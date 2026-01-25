import asyncio
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger("WEATHER_FORECAST")

# URL CORRIGÉE : Page climat/météo par ville
BASE_URL = "https://meteoburkina.bf/le-climat-de-nos-villes/"
PLAYWRIGHT_TIMEOUT = 30000

class WeatherForecastService:
    """
    Service pour scraper les données météo par ville en utilisant Playwright.
    Adapté à la structure avec menu déroulant (#city_select).
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.structured_forecasts: List[Dict[str, Any]] = []

    def _scrape_forecasts(self, page: Page) -> List[Dict[str, Any]]:
        """
        Scrape les données pour chaque ville disponible dans le menu déroulant, en extrayant t_min, t_max, précip.
        """
        forecasts = []
        try:
            select_selector = "#city_select"
            page.wait_for_selector(select_selector, state="attached", timeout=15000)

            options = page.locator(f"{select_selector} option").all()
            cities_to_scrape = []
            for opt in options:
                val = opt.get_attribute("value")
                label = opt.inner_text().strip()
                if val:
                    cities_to_scrape.append((val, label))

            logger.info(f"Villes trouvées dans le menu : {len(cities_to_scrape)}")


            for city_val, city_name in cities_to_scrape:
                try:
                    logger.info(f"Scraping pour : {city_name}")
                    page.select_option(select_selector, city_val)
                    page.wait_for_timeout(2000)

                    # Force la sélection des cases à cocher pour chaque paramètre
                    for param in ["Température minimale", "Température maximale", "Précipitation"]:
                        try:
                            # Cherche le label exact et clique dessus si décoché
                            label = page.locator(f'label:has-text("{param}")').first
                            if label.count() > 0:
                                checkbox = label.locator('input[type="checkbox"]').first
                                if checkbox.count() > 0 and not checkbox.is_checked():
                                    checkbox.check()
                        except Exception as e:
                            logger.warning(f"Impossible de cocher '{param}' pour {city_name}: {e}")

                    page.wait_for_timeout(1000)


                    # Diagnostic : lister tous les noms de séries Highcharts pour cette ville
                    series_names = page.evaluate('''() => {
                        if (!window.Highcharts) return [];
                        const charts = Highcharts.charts.filter(c => c);
                        if (!charts.length) return [];
                        const chart = charts[0];
                        return chart.series.map(s => s.name);
                    }''')
                    logger.info(f"Highcharts series for {city_name}: {series_names}")

                    # Extraction JS des séries Highcharts avec noms exacts
                    series_data = page.evaluate('''() => {
                        if (!window.Highcharts) return null;
                        const charts = Highcharts.charts.filter(c => c);
                        if (!charts.length) return null;
                        const chart = charts[0];
                        const result = {};
                        chart.series.forEach(s => {
                            // Normalise les espaces multiples
                            const name = (s.name || '').toLowerCase().replace(/\s+/g, ' ').trim();
                            if (name.includes('température minimale')) result['t_min'] = s.data.map(pt => pt.y);
                            if (name.includes('température maximale')) result['t_max'] = s.data.map(pt => pt.y);
                            if (name.includes('précipitation')) result['precip'] = s.data.map(pt => pt.y);
                        });
                        return result;
                    }''')

                    forecast_data = {
                        "city": city_name,
                        "t_min": series_data.get('t_min') if series_data and 't_min' in series_data else None,
                        "t_max": series_data.get('t_max') if series_data and 't_max' in series_data else None,
                        "precip": series_data.get('precip') if series_data and 'precip' in series_data else None,
                        "source_url": BASE_URL
                    }

                    content_preview = f"Données climatiques extraites pour {city_name} (t_min, t_max, précip)."

                    forecasts.append({
                        'city': city_name,
                        'content_preview': content_preview,
                        'data_path': f"/data/weather/climat_{city_name.lower().replace(' ', '_')}.json",
                        'full_data': json.dumps(forecast_data, ensure_ascii=False)
                    })

                except Exception as e:
                    logger.error(f"Erreur lors du traitement de {city_name}: {e}")
                    continue

            if not forecasts:
                logger.warning("Aucune donnée extraite via le menu déroulant.")

            return forecasts

        except PlaywrightTimeoutError:
            logger.error(f"Timeout: Le sélecteur {select_selector} n'a pas été trouvé.")
            return []
        except Exception as e:
            logger.error(f"Erreur inattendue lors du scraping des prévisions: {e}")
            return []

    def scrape_forecast(self) -> Dict[str, Any]:
        """
        Méthode principale pour orchestrer le scraping.
        """
        self.structured_forecasts = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()

            logger.info(f"Navigation vers la page des prévisions: {BASE_URL}")
            try:
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)
                
                # Gestion des popups éventuels
                try:
                    page.locator(".dialog-close-button, .close-popup").click(timeout=2000)
                except:
                    pass

                self.structured_forecasts = self._scrape_forecasts(page)
                
            except Exception as e:
                logger.error(f"Erreur globale de scraping: {e}")
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

def run_scrape_forecast() -> Dict[str, Any]:
    return WeatherForecastService(headless=True).scrape_forecast()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = WeatherForecastService(headless=False).scrape_forecast()
    with open("data/weather_service_latest.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print("✅ Données météo écrites dans data/weather_service_latest.json")