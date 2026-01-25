
import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin
from typing import List, Dict, Any, Optional
from datetime import datetime
import io

# Setup logger
logger = logging.getLogger("Scraper.MeteoBurkina")

try:
    from pypdf import PdfReader
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

class MeteoBurkinaScraper:
    """
    Scraper spécialisé pour le portail MeteoBurkina.bf.
    Cible : Bulletins Quotidiens (Alerte) et Décadaires (Agro).
    """
    
    BASE_URL = "https://meteoburkina.bf"
    
    SOURCES = [
        {
            "name": "Bulletin Quotidien",
            "url": "produits/bulletin-quotidien/",
            "type": "METEO_ALERT",
            "priority": "HIGH"
        },
        {
            "name": "Bulletin Agrométéorologique",
            "url": "produits/bulletin-agrometeologique-decadaire/",
            "type": "AGRI_REPORT",
            "priority": "MEDIUM"
        }
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AgriConnect-Sentinelle/1.0 (Education/Research; contact@agriconnect.bf)"
        })

    def run(self) -> List[Dict[str, Any]]:
        """
        Exécute le scraping de toutes les sources configurées.
        """
        results = []
        logger.info(f"⛈️ Démarrage du scraping MeteoBurkina ({len(self.SOURCES)} sources)...")
        
        for source in self.SOURCES:
            try:
                logger.info(f"Scanning {source['name']}...")
                doc = self._process_source(source)
                if doc:
                    results.append(doc)
            except Exception as e:
                logger.error(f"Erreur source {source['name']}: {e}")
                
        logger.info(f"✅ Scraping terminé. {len(results)} documents récupérés.")
        return results

    def _process_source(self, source: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Traite une catégorie de bulletin (ex: Quotidien).
        Retourne le DERNIER bulletin valide trouvé.
        """
        index_url = urljoin(self.BASE_URL, source["url"])
        
        # 1. Récupération liste des articles
        try:
            resp = self.session.get(index_url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            logger.warning(f"Impossible d'accéder à {index_url}: {e}")
            return None

        # 2. Trouver le dernier article (le plus récent)
        # Structure supposée: <div class="post"> ... <a href="...">Lire plus</a>
        # On cherche tous les liens qui contiennent le chemin de la source
        candidates = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Heuristique : le lien doit être plus long que l'index et contenir le nom du produit
            if source["url"].strip('/') in href and len(href) > len(source["url"]) + 5:
                candidates.append(urljoin(self.BASE_URL, href))
        
        # On prend le premier candidat (souvent le plus rÃ©cent en haut de liste)
        # TODO: Vérifier dates si possible
        if not candidates:
            logger.info(f"Aucun article trouvé pour {source['name']}")
            return None
            
        latest_article_url = candidates[0]
        logger.info(f"Article détecté: {latest_article_url}")
        
        return self._extract_bulletin_content(latest_article_url, source)

    def _extract_bulletin_content(self, article_url: str, source_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Entre dans la page de l'article et cherche le PDF ou extrait le texte.
        """
        try:
            resp = self.session.get(article_url, timeout=20)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 1. Chercher un lien PDF ("Télécharger", ".pdf")
            pdf_link = None
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.lower().endswith('.pdf') or "télécharger" in a.text.lower():
                    pdf_link = urljoin(self.BASE_URL, href)
                    break
            
            content_text = ""
            
            # 2. Si PDF trouvé -> Extraction
            if pdf_link and HAS_PYPDF2:
                logger.info(f"PDF trouvé: {pdf_link}")
                content_text = self._download_and_parse_pdf(pdf_link)
            
            # 3. Fallback : Texte de la page HTML
            if not content_text or len(content_text) < 50:
                logger.info("Fallback sur contenu HTML")
                # Extraction basique des paragraphes
                paragraphs = [p.get_text() for p in soup.find_all('p')]
                content_text = "\n".join(paragraphs)
            
            # Construction du document standardisé
            title = soup.title.string.strip() if soup.title else source_info["name"]
            
            return {
                "source_type": source_info["type"], # Clé pour le Vector Store (METEO_ALERT...)
                "title": title,
                "url": article_url,
                "created_at": datetime.now().isoformat(),
                "content": content_text,
                "metadata": {
                    "provider": "ANAM-BF",
                    "priority": source_info["priority"],
                    "original_pdf": pdf_link
                }
            }
            
        except Exception as e:
            logger.error(f"Echec extraction {article_url}: {e}")
            return None

    def _download_and_parse_pdf(self, pdf_url: str) -> str:
        try:
            r = self.session.get(pdf_url, timeout=30)
            f = io.BytesIO(r.content)
            reader = PdfReader(f)
            text = []
            # On prend max 3 pages pour éviter le bruit
            for page in reader.pages[:3]:
                text.append(page.extract_text())
            return "\n".join(text)
        except Exception as e:
            logger.warning(f"Erreur parsing PDF: {e}")
            return ""

if __name__ == "__main__":
    # Test unitaire rapide
    scraper = MeteoBurkinaScraper()
    docs = scraper.run()
    for d in docs:
        print(f"--- {d['title']} ---")
        print(d['content'][:200] + "...")
