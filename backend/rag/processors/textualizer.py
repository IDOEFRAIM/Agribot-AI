
import json
import logging
import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Generator
from datetime import datetime

# --- Configuration du Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AgriConnect.Preprocessor")

class GenericBulletinProcessor:
    """
    Analyse et synthétise le texte brut des bulletins agricoles.
    """
    
    # Patterns Regex optimisés pour le contexte sahélien/Burkina
    PATTERNS = {
        "météo": r"(conditions\s+m[ée]t[ée]orologiques|pluviom[ée]trie|pr[ée]visions).*?(?=\.|$|perspectives|avis|conseils|prix|march[ée])",
        "marché": r"(prix\s+des\s+produits|march[ée]s?|cours\s+mondiaux).*?(?=\.|$|perspectives|avis|conseils|m[ée]t[ée]o)",
        "conseils": r"(avis\s+et\s+conseils|recommandations|techniques\s+culturales).*?(?=\.|$|perspectives|prix|march[ée])",
    }

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Nettoie les espaces, sauts de ligne et caractères spéciaux."""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def summarize(cls, text: str, max_length: int = 800) -> str:
        """Extrait les sections clés ou tronque le texte si aucune section n'est trouvée."""
        cleaned = cls.clean_text(text)
        summary_parts = []

        for label, pattern in cls.PATTERNS.items():
            match = re.search(pattern, cleaned, re.IGNORECASE | re.DOTALL)
            if match:
                summary_parts.append(f"[{label.upper()}] {match.group(0).strip()}")

        if not summary_parts:
            return cleaned[:max_length] + ("..." if len(cleaned) > max_length else "")
        
        return "\n".join(summary_parts)


class Textualizer:
    def __init__(self, data_dir='data', output_path='data/texts_for_chunking.json'):
        self.data_dir = data_dir
        self.output_path = output_path

    def extract_texts(self) -> List[Dict]:
        """
        Parcourt tous les fichiers JSON du dossier data/ et extrait les textes pertinents.
        Retourne une liste de dicts {zone_id/file/thème, text_content, source_type, ...}
        """
        results = []
        for fname in os.listdir(self.data_dir):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(self.data_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Extraction selon le format du fichier
                if isinstance(data, list):
                    for entry in data:
                        # PDF chunks
                        if 'text_content' in entry:
                            d = {
                                'text_content': entry['text_content'],
                                'source_type': entry.get('source_type', 'PDF_BULLETIN'),
                                'file': entry.get('file'),
                                'zone_id': entry.get('zone_id'),
                                'meta': {k: v for k, v in entry.items() if k not in ['text_content', 'file', 'zone_id', 'source_type']}
                            }
                            results.append(d)
                elif isinstance(data, dict):
                    # METEO_VECTOR ou autres
                    for v in data.values():
                        if isinstance(v, dict) and 'text_content' in v:
                            d = {
                                'text_content': v['text_content'],
                                'source_type': v.get('source_type', 'UNKNOWN'),
                                'file': v.get('file'),
                                'zone_id': v.get('zone_id'),
                                'meta': {k: val for k, val in v.items() if k not in ['text_content', 'file', 'zone_id', 'source_type']}
                            }
                            results.append(d)
            except Exception as e:
                print(f"Erreur lecture {fname}: {e}")
        return results

    def save_texts(self, texts: List[Dict]):
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(texts, f, ensure_ascii=False, indent=2)

    def run(self):
        texts = self.extract_texts()
        self.save_texts(texts)
        print(f"{len(texts)} textes extraits et sauvegardés dans {self.output_path}")

# --- Exemple d'utilisation ---
# textualizer = Textualizer(data_dir='data', output_path='data/texts_for_chunking.json')
# textualizer.run()

def preprocess_all_data(
    input_dir: str = "data",
    output_filename: str = "preprocessed_bulletins.json",
    max_entries_per_file: int = 1000
):
    """
    Pipeline principal : parcourt, traite et sauvegarde les données.
    """
    # Correction : base_path = racine du projet
    base_path = Path(__file__).resolve().parent.parent.parent
    data_path = (base_path / input_dir).resolve()
    output_path = data_path / output_filename

    files_to_process = [
        'all_pdfs_extracted.json',
        'all_pdfs_chunks.json',
        'document_scraper_latest.json',
    ]

    final_results = []

    for filename in files_to_process:
        file_path = data_path / filename
        if not file_path.exists():
            logger.warning(f"Fichier manquant ignoré : {filename}")
            continue

        logger.info(f"Traitement de {filename}...")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for i, entry in enumerate(data):
                if i >= max_entries_per_file: break
                # Extraction directe du texte selon la structure
                if 'pages' in entry:
                    for page in entry['pages']:
                        raw_text = page.get('text', '')
                        if not raw_text.strip(): continue
                        summary = GenericBulletinProcessor.summarize(raw_text)
                        final_results.append({
                            "source_file": filename,
                            "identifier": entry.get('file') or entry.get('url') or "unknown",
                            "processed_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
                            "summary": summary
                        })
                elif 'text_content' in entry:
                    raw_text = entry['text_content']
                    if not raw_text.strip(): continue
                    summary = GenericBulletinProcessor.summarize(raw_text)
                    final_results.append({
                        "source_file": filename,
                        "identifier": entry.get('file') or entry.get('url') or "unknown",
                        "processed_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
                        "summary": summary
                    })
                elif 'content' in entry:
                    raw_text = entry['content']
                    if not raw_text.strip(): continue
                    summary = GenericBulletinProcessor.summarize(raw_text)
                    final_results.append({
                        "source_file": filename,
                        "identifier": entry.get('file') or entry.get('url') or "unknown",
                        "processed_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
                        "summary": summary
                    })
        except Exception as e:
            logger.error(f"Erreur lors du traitement de {filename} : {e}")

    # Sauvegarde finale
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2)
        logger.info(f"Succès : {len(final_results)} résumés sauvegardés dans {output_path}")
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde : {e}")

if __name__ == "__main__":
    from datetime import datetime
    preprocess_all_data()