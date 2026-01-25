import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
import re
import sys

def fetch_html(url, headers=None):
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERR] Erreur lors de la connexion à {url} : {e}")
        return None

def extract_bulletin_links(main_url, headers=None):
    html = fetch_html(main_url, headers)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        # On prend les liens internes qui mènent à un bulletin (souvent dans le même dossier)
        if main_url.rstrip('/') in urljoin(main_url, href):
            title = a.text.strip() or a.get("title", "")
            links.append({"detail_url": urljoin(main_url, href), "title": title})
    return links

def extract_pdf_from_detail(detail_url, headers=None):
    html = fetch_html(detail_url, headers)
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

def download_pdf(pdf_url, out_dir, headers=None):
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
        print(f"[ERR] Échec téléchargement {pdf_url} : {e}")
        return None

def scrape_bulletins(main_url, out_dir, headers=None):
    bulletins = extract_bulletin_links(main_url, headers)
    results = []
    for b in bulletins:
        pdf_url, date = extract_pdf_from_detail(b["detail_url"], headers)
        if pdf_url:
            local_path = download_pdf(pdf_url, out_dir, headers)
            results.append({
                "pdf_url": pdf_url,
                "local_path": local_path,
                "detail_url": b["detail_url"],
                "title": b["title"],
                "date": date
            })
    return results

if __name__ == "__main__":
    # Utilisation : python scraper_template.py <URL_PRODUIT> <DOSSIER_PDF>
    if len(sys.argv) < 3:
        print("Usage: python scraper_template.py <URL_PRODUIT> <DOSSIER_PDF>")
        sys.exit(1)
    url = sys.argv[1]
    out_dir = sys.argv[2]
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    results = scrape_bulletins(url, out_dir, HEADERS)
    print(f"[RESUME] {len(results)} bulletins PDF téléchargés.")
