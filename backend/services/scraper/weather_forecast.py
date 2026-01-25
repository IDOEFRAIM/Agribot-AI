
import logging
import json
import os
import sys
import time
from typing import List, Dict, Any, Optional, Callable
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError


# --- Orchestrateur avec config centralisée ---
class WeatherForecastOrchestrator:
    """
    Orchestrateur pour le scraping météo (WeatherForecastService).
    Permet d'exécuter le scraping, de logger, et de sauvegarder les résultats.
    """
    DEFAULT_CONFIG = {
        "BASE_URL": "https://meteoburkina.bf/le-climat-de-nos-villes/",
        "PLAYWRIGHT_TIMEOUT": 60000,  # ms
        "HEADLESS": True,
        "SELECTOR_CITY": "#city_select",
        "WAIT_CITY_SELECTOR": 15000,  # ms
        "WAIT_GRAPH_UPDATE": 2000,    # ms
        "LOG_FILE": "weather_forecast_orchestrator.log",
    }

    def __init__(self, headless: bool = True, config: dict = None):
        self.config = self.DEFAULT_CONFIG.copy()
        if config:
            self.config.update(config)
        if headless is not None:
            self.config["HEADLESS"] = headless
        os.makedirs(os.path.dirname(self.config["LOG_FILE"]) or '.', exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config["LOG_FILE"], mode='w', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger("WeatherForecastOrchestrator")
        self.forecast_scraper = WeatherForecastService(self.config, logger=self.logger)

    def run(self) -> Dict[str, Any]:
        self.logger.info("===== DÉMARRAGE DU SCRAPING MÉTÉO =====")
        start_time = time.time()
        try:
            result = self.forecast_scraper.scrape_forecast()
            status = result.get('status', 'UNKNOWN')
            self.logger.info(f"Statut: {status}, Message: {result.get('message', 'N/A')}")
            self.logger.info(f"Nombre de villes: {len(result.get('results', []))}")
        except Exception as e:
            self.logger.error(f"Erreur critique lors du scraping météo: {e}", exc_info=True)
            result = {"status": "CRITICAL_ERROR", "message": str(e), "results": []}
        duration = time.time() - start_time
        self.logger.info(f"Durée totale: {duration:.2f} secondes.")
        self.logger.info("===== FIN DU SCRAPING MÉTÉO =====")
        return result


class WeatherForecastService:
    """
    Service pour scraper les données météo par ville en utilisant Playwright.
    Extrait les données climatiques (températures, précipitations) depuis les graphiques Highcharts.
    """

    def __init__(self, config: dict, logger=None):
        self.config = config.copy()
        self.headless = self.config["HEADLESS"]
        self.structured_forecasts: List[Dict[str, Any]] = []
        self.logger = logger or logging.getLogger("WeatherForecastOrchestrator")

    def _extract_highcharts_data(self, page: Page) -> Dict[str, Any]:
        """
        Tente d'extraire les données brutes des graphiques Highcharts présents sur la page.
        """
        try:
            # Script pour récupérer les données de tous les graphiques Highcharts sur la page
            data = page.evaluate("""() => {
                const charts = [];
                if (window.Highcharts && window.Highcharts.charts) {
                    window.Highcharts.charts.forEach((chart, index) => {
                        if (chart) {
                            const seriesData = chart.series.map(s => ({
                                name: s.name,
                                data: s.data.map(p => ({
                                    category: p.category,
                                    y: p.y,
                                    x: p.x
                                }))
                            }));
                            charts.push({
                                title: chart.title ? chart.title.textStr : `Graphique ${index}`,
                                subtitle: chart.subtitle ? chart.subtitle.textStr : '',
                                series: seriesData
                            });
                        }
                    });
                }
                return charts;
            }""")
            return data
        except Exception as e:
            self.logger.warning(f"Impossible d'extraire les données Highcharts: {e}")
            return {}

    def _scrape_forecasts(self, page: Page) -> List[Dict[str, Any]]:
        """
        Scrape les données pour chaque ville disponible dans le menu déroulant.
        """
        forecasts = []
        try:
            # 1. Attendre et localiser le menu déroulant des villes
            select_selector = self.config["SELECTOR_CITY"]
            try:
                page.wait_for_selector(select_selector, state="attached", timeout=self.config["WAIT_CITY_SELECTOR"])
            except PlaywrightTimeoutError:
                self.logger.error(f"Sélecteur {select_selector} introuvable. La structure de la page a peut-être changé.")
                return []
            # Récupérer toutes les options de villes
            options = page.locator(f"{select_selector} option").all()
            cities_to_scrape = []
            for opt in options:
                val = opt.get_attribute("value")
                label = opt.inner_text().strip()
                if val: 
                    cities_to_scrape.append((val, label))
            self.logger.info(f"Villes trouvées dans le menu : {len(cities_to_scrape)}")

            # Limiter le nombre de villes pour le test/démo si nécessaire, sinon tout scraper
            # cities_to_scrape = cities_to_scrape[:3] 

            # 2. Itérer sur chaque ville
            for city_val, city_name in cities_to_scrape:
                try:
                    self.logger.info(f"Scraping pour : {city_name}")
                    # Sélectionner la ville
                    page.select_option(select_selector, city_val)
                    
                    # Attendre que le contenu se mette à jour (AJAX)
                    # On attend un peu pour laisser le temps au JS de mettre à jour le graphique
                    page.wait_for_timeout(self.config["WAIT_GRAPH_UPDATE"]) 
                    
                    # Extraction des données Highcharts
                    charts_data = self._extract_highcharts_data(page)
                    
                    # Construction du résumé textuel
                    content_summary = f"Données climatiques pour {city_name}.\n"
                    if charts_data:
                        for chart in charts_data:
                            content_summary += f"Graphique: {chart.get('title', 'N/A')}\n"
                            for serie in chart.get('series', []):
                                content_summary += f"- {serie.get('name', 'Série')}: {len(serie.get('data', []))} points de données.\n"
                    else:
                        content_summary += "Aucune donnée graphique extraite.\n"

                    # Création de l'objet résultat standardisé
                    forecast_entry = {
                        "url": self.config["BASE_URL"],
                        "type": "weather_data",
                        "title": f"Climat - {city_name}",
                        "content": content_summary,
                        "metadata": {
                            "city": city_name,
                            "raw_data": charts_data
                        }
                    }
                    
                    forecasts.append(forecast_entry)
                    
                except Exception as e:
                    self.logger.error(f"Erreur lors du traitement de {city_name}: {e}")
                    continue

            if not forecasts:
                self.logger.warning("Aucune donnée extraite via le menu déroulant.")
                
            return forecasts

        except Exception as e:
            self.logger.error(f"Erreur inattendue lors du scraping des prévisions: {e}")
            return []

    def scrape_forecast(self) -> Dict[str, Any]:
        """
        Méthode principale pour orchestrer le scraping.
        """
        self.structured_forecasts = []
        

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            page = context.new_page()

            self.logger.info(f"Navigation vers la page des prévisions: {self.config['BASE_URL']}")
            try:
                page.goto(self.config["BASE_URL"], wait_until="domcontentloaded", timeout=self.config["PLAYWRIGHT_TIMEOUT"])
                try:
                    page.locator(".dialog-close-button, .close-popup, #cookie-accept").click(timeout=2000)
                except:
                    pass
                self.structured_forecasts = self._scrape_forecasts(page)
            except Exception as e:
                self.logger.error(f"Erreur globale de scraping: {e}")
            finally:
                browser.close()

        if not self.structured_forecasts:
            return {
                "status": "ERROR",
                "message": "Échec de l'extraction des données météo.",
                "results": []
            }
        else:
            return {
                "status": "SUCCESS",
                "message": f"{len(self.structured_forecasts)} villes collectées.",
                "results": self.structured_forecasts
            }


# --- Point d'entrée CLI ---
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Orchestrateur de scraping météo (WeatherForecastService)")
    parser.add_argument('--headless', action='store_true', default=True, help='Mode headless pour le navigateur (par défaut: True)')
    parser.add_argument('--output', type=str, default="weather_forecast_results.json", help='Fichier de sortie JSON')
    parser.add_argument('--timeout', type=int, default=None, help='Timeout Playwright (ms)')
    parser.add_argument('--base_url', type=str, default=None, help='URL cible à scraper')
    parser.add_argument('--wait_city_selector', type=int, default=None, help='Timeout attente menu ville (ms)')
    parser.add_argument('--wait_graph_update', type=int, default=None, help='Timeout attente update graphique (ms)')
    args = parser.parse_args()

    config_override = {}
    if args.timeout is not None:
        config_override["PLAYWRIGHT_TIMEOUT"] = args.timeout
    if args.base_url is not None:
        config_override["BASE_URL"] = args.base_url
    if args.wait_city_selector is not None:
        config_override["WAIT_CITY_SELECTOR"] = args.wait_city_selector
    if args.wait_graph_update is not None:
        config_override["WAIT_GRAPH_UPDATE"] = args.wait_graph_update

    orchestrator = WeatherForecastOrchestrator(headless=args.headless, config=config_override)
    result = orchestrator.run()
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[OK] Résultats sauvegardés dans {args.output}")
