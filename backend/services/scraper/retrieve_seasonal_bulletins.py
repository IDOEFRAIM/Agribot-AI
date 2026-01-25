import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
import re

# --- CONFIGURATION ---
TARGET_URL = "https://meteoburkina.bf/produits/bulletin-de-previsions-saisonnieres/"
OUTPUT_PATH = "data/seasonal_bulletins_links.txt"
PDF_DIR = "data/seasonal_bulletins_pdfs"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def fetch_html(url):
    """Récupère le contenu HTML d'une page."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status() # Génère une erreur si le statut est 4xx ou 5xx
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"[-] Erreur lors de la connexion à {url} : {e}")
        return None

def extract_links(html, base_url):
    """Extrait les liens PDF/bulletins, titres et dates, et les convertit en liens absolus."""
    soup = BeautifulSoup(html, "html.parser")
    found_docs = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        is_detail = "bulletin" in href.lower() or "communique" in href.lower()
        if is_detail:
            full_url = urljoin(base_url, href)
            title = a.text.strip() or a.get("title", "")
            date_match = re.search(r"(\d{4})", title + href)
            date = date_match.group(1) if date_match else ""
            found_docs.append({"detail_url": full_url, "title": title, "date": date})
    return found_docs

def save_links(docs, file_path):
    """Enregistre la liste des liens, titres et dates dans un fichier texte."""
    if not docs:
        print("[!] Aucun document à enregistrer.")
        return
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for doc in docs:
                url = doc.get('pdf_url') or doc.get('detail_url')
                f.write(f"{url}\t{doc.get('title','')}\t{doc.get('date','')}\n")
        print(f"[+] {len(docs)} documents trouvés. Liste enregistrée dans : {file_path}")
    except IOError as e:
        print(f"[-] Erreur lors de l'écriture du fichier : {e}")

def download_pdfs(docs, pdf_dir):
    """Télécharge tous les PDF dans le dossier pdf_dir."""
    os.makedirs(pdf_dir, exist_ok=True)
    total = 0
    for doc in docs:
        detail_url = doc["detail_url"]
        try:
            detail_html = fetch_html(detail_url)
            if not detail_html:
                print(f"[ERR] Impossible de charger la page détail : {detail_url}")
                continue
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            pdf_link = None
            for a in detail_soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().endswith(".pdf") or "telecharger-le-document" in href.lower():
                    pdf_link = urljoin(detail_url, href)
                    break
            if not pdf_link:
                print(f"[ERR] Aucun PDF trouvé sur : {detail_url}")
                continue
            filename = os.path.join(pdf_dir, os.path.basename(pdf_link))
            if os.path.exists(filename):
                print(f"[SKIP] Déjà téléchargé : {filename}")
                continue
            print(f"[DL] Téléchargement : {pdf_link}")
            r = requests.get(pdf_link, headers=HEADERS, timeout=30)
            r.raise_for_status()
            with open(filename, "wb") as f:
                f.write(r.content)
            print(f"[OK] Sauvé : {filename}")
            total += 1
        except Exception as e:
            print(f"[ERR] Échec téléchargement {detail_url} : {e}")
    print(f"[RESUME] {total} PDF téléchargés dans {pdf_dir}")

# --- POINT D'ENTRÉE DU SCRIPT ---
def main():
    print(f"[*] Début du scan de : {TARGET_URL}")
    html_content = fetch_html(TARGET_URL)
    if html_content:
        docs = extract_links(html_content, TARGET_URL)
        save_links(docs, OUTPUT_PATH)
        download_pdfs(docs, PDF_DIR)

if __name__ == "__main__":
    main()