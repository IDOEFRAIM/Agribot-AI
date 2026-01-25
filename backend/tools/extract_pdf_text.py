import os
import json

import pdfplumber
from glob import glob
import pytesseract
from PIL import Image
# Chemin explicite pour Tesseract sous Windows
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

def extract_text_from_pdf(pdf_path):
    """Extrait le texte et le texte OCR de chaque page d'un PDF."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_results = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                ocr_texts = []
                # Extraire les images de la page et appliquer l'OCR
                page_bbox = (page.bbox[0], page.bbox[1], page.bbox[2], page.bbox[3])
                for img in page.images:
                    # Vérifier que la bounding box de l'image est entièrement dans la page
                    img_bbox = (img["x0"], img["top"], img["x1"], img["bottom"])
                    if (
                        img_bbox[0] >= page_bbox[0] and img_bbox[1] >= page_bbox[1] and
                        img_bbox[2] <= page_bbox[2] and img_bbox[3] <= page_bbox[3]
                    ):
                        try:
                            cropped = page.crop(img_bbox)
                            pil_img = cropped.to_image(resolution=300).original
                            ocr_text = pytesseract.image_to_string(pil_img, lang="fra+eng")
                            if ocr_text.strip():
                                ocr_texts.append(ocr_text.strip())
                        except Exception as e:
                            print(f"[ERR] OCR image page: {e}")
                    else:
                        print(f"[SKIP] Image hors page : {img_bbox} vs {page_bbox}")
                page_results.append({
                    "text": text,
                    "ocr_images_text": ocr_texts
                })
            return page_results
    except Exception as e:
        print(f"[ERR] Extraction échouée pour {pdf_path} : {e}")
        return []

def extract_all_pdfs(pdf_dir, output_json):
    """Parcourt récursivement tous les PDF d'un dossier et ses sous-dossiers, extrait le texte et le texte OCR des images, et sauvegarde en JSON."""
    results = []
    for root, _, files in os.walk(pdf_dir):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_path = os.path.join(root, file)
                print(f"[EXTRACT] {pdf_path}")
                pages = extract_text_from_pdf(pdf_path)
                results.append({
                    "file": file,
                    "path": pdf_path,
                    "nb_pages": len(pages),
                    "pages": pages
                })
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[OK] Extraction terminée. Résultat : {output_json}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python extract_pdf_text.py <dossier_pdfs> <output.json>")
        exit(1)
    extract_all_pdfs(sys.argv[1], sys.argv[2])
