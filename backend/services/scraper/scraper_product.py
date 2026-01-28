import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
import re
import sys



class ScrapperProduct:
    def __init__(self,out_dir,urls,headers=None,):
        self.urls = urls
        self.out_dir = out_dir
        self.headers = headers

    def fetch_html(self,url, headers=None):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"[ERR] Erreur lors de la connexion à {url} : {e}")
            return None

    def extract_bulletin_links(self,main_url, headers=None):
        html = self.fetch_html(main_url, headers)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            # On prend les liens internes qui mènent à un bulletin 
            if main_url.rstrip('/') in urljoin(main_url, href):
                title = a.text.strip() or a.get("title", "")
                links.append({"detail_url": urljoin(main_url, href), "title": title})
        return links


    def extract_pdf_from_detail(self,detail_url, headers=None):
        html = self.fetch_html(detail_url, headers)
        if not html:
            return None, None
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().endswith(".pdf") or "telecharger-le-document" in href.lower():
                pdf_url = urljoin(detail_url, href)
                # Titre et date (si trouvable)
                title = soup.title.text.strip() if soup.title else ""
                date_match = re.search(r"(\d{4})", title + href)
                date = date_match.group(1) if date_match else ""
                return pdf_url, date
        return None, None

    def download_pdf(self,pdf_url, out_dir, headers=None):
        os.makedirs(out_dir, exist_ok=True)
        filename = os.path.join(out_dir, os.path.basename(pdf_url))
        if os.path.exists(filename):
            print(f"[SKIP] Déjà téléchargé : {filename}")
            return filename
        try:
            print(f"[DL] {pdf_url}")
            r = requests.get(pdf_url, headers=headers, timeout=30)
            r.raise_for_status()
            with open(filename, "wb") as f:
                f.write(r.content)
            print(f"[OK] Sauvé : {filename}")
            return filename
        except Exception as e:
            print(f"ERROR: Échec téléchargement {pdf_url} : {e}")
            return None

    def scrape_bulletins(self,url):
        bulletins = self.extract_bulletin_links(url, self.headers)
        results = []
        for b in bulletins:
            pdf_url, date = self.extract_pdf_from_detail(b["detail_url"], self.headers)
            if pdf_url:
                local_path = self.download_pdf(pdf_url, self.out_dir, self.headers)
                results.append({
                    "pdf_url": pdf_url,
                    "local_path": local_path,
                    "detail_url": b["detail_url"],
                    "title": b["title"],
                    "date": date
                })
        return results
    
    def run(self):
        all_results = []
        for url in self.urls:
            print('='*20,'STARTING SCRAPING','='*50)
            print('On commence a scrapper les documents de:',url)
            folder = "backend/sources/raw_data/" + url.split("/")[-2]
            print(f"Scraping {url} -> {folder}")
            results = self.scrape_bulletins(url)
            all_results.extend(results)
            print(f"[RESUME] {len(results)} bulletins PDF téléchargés.")
            print('='*20,'We successfully scrape docs','='*50)
        return all_results


if __name__ == "__main__":
    urls = [
    "https://meteoburkina.bf/produits/bulletin-mensuel/",
    "https://meteoburkina.bf/produits/etat-annuel-du-climat/",
    "https://meteoburkina.bf/produits/bulletin-hebdomadaire/",
    "https://meteoburkina.bf/produits/bulletin-agrometeorologique-mensuel/",
    "https://meteoburkina.bf/produits/bulletin-quotidien/",
    "https://meteoburkina.bf/produits/bulletin-eau-energie/",
    "https://meteoburkina.bf/produits/bulletin-climatique-mensuel/",
    "https://meteoburkina.bf/produits/bulletin-agrometeo-pour-les-medias/",
    "https://meteoburkina.bf/produits/climat-du-burkina-faso/",
    "https://meteoburkina.bf/produits/bulletin-climat-sante/",
    "https://meteoburkina.bf/produits/bulletin-de-previsions-saisonnieres/",
    "https://meteoburkina.bf/produits/bulletin-agrometeologique-decadaire/"
    ]

    scraper = ScrapperProduct( "backend/sources/raw_data/",urls, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    scraper.run()  
            

         

