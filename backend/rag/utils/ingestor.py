# --- Entrée principale pour exécution directe ---
"""
RAG Pipeline Overview:

1. Ingestor (load, preprocess, chunk):
    - Loads raw data (PDF/JSON/CSV)
    - Preprocesses (cleans/structures) the data
    - Chunks the cleaned data for retrieval
2. Vector Store:
    - Chunks are embedded and stored for fast similarity search
3. Retrieve:
    - Given a query, relevant chunks are retrieved from the vector store
4. Reranking:
    - Retrieved chunks are reranked (optionally with LLM or scoring)

This file implements the Ingestor step (load, preprocess, chunk).
"""
import os
import json
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import requests

# Import pour pipeline explicite
from rag.processors.textualizer import preprocess_all_data
from rag.utils.chunker import Chunker



# --- Configuration & Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("rag.Ingestor")

DEFAULT_CONFIG = {
    "CHUNK_SIZE": 500,
    "CHUNK_OVERLAP": 50,
}

# --- Nettoyage LLM via Ollama ---
class OllamaCleaner:
    """
    Utilise un LLM local via Ollama pour nettoyer et reformuler les textes extraits de l'OCR.
    """
    def __init__(self, model="llama3", host="http://localhost:11434"):
        self.model = model
        self.host = host

    def clean(self, text: str) -> str:
        prompt = (
            "Nettoie et reformule ce texte issu d'un OCR de bulletin agricole. "
            "Supprime le bruit, corrige les erreurs, reconstitue des phrases lisibles et ne garde que les informations utiles pour un humain :\n" + text
        )
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", text)
        except Exception as e:
            logger.warning(f"Ollama LLM cleaning failed: {e}")
            return text

class GenericIngestor:

    """
    Ingestor universel pour pipeline RAG.
    Supporte les formats : PDF (via JSON structuré), JSON générique et CSV.
    """
    def __init__(self, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None):
        self.chunk_size = chunk_size or DEFAULT_CONFIG["CHUNK_SIZE"]
        self.chunk_overlap = chunk_overlap or DEFAULT_CONFIG["CHUNK_OVERLAP"]
        self.chunker = Chunker(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)

    def preprocess_and_chunk(self, input_dir: str = "data", preprocessed_dir: str = "data/preprocessed", chunked_dir: str = "data/chunked"):
        """
        Prétraite et découpe chaque fichier JSON du dossier input_dir individuellement.
        """
        os.makedirs(preprocessed_dir, exist_ok=True)
        os.makedirs(chunked_dir, exist_ok=True)

        def preprocess_single_json(input_path: str, output_path: str):
            """Prétraite un seul fichier JSON et sauvegarde le résultat. Extraction récursive de tous les champs textuels pertinents."""
            try:
                with open(input_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results = []
                from rag.processors.textualizer import GenericBulletinProcessor

                def recursive_extract(entry, identifier_hint=None):
                    # If entry is a dict, look for all string fields and recurse
                    if isinstance(entry, dict):
                        for k, v in entry.items():
                            if isinstance(v, str):
                                raw_text = v.strip()
                                # Skip links, html tags, and generic titles
                                if raw_text and not raw_text.startswith('http') and raw_text.lower() not in ['html', 'bulletin', 'bulletin mensuel', 'bulletin agrométéorologique mensuel']:
                                    # If HTML, extract visible text
                                    if '<html' in raw_text.lower() or '<body' in raw_text.lower():
                                        try:
                                            from bs4 import BeautifulSoup
                                            soup = BeautifulSoup(raw_text, 'html.parser')
                                            visible_text = soup.get_text(separator=' ', strip=True)
                                            summary = GenericBulletinProcessor.summarize(visible_text)
                                        except Exception:
                                            summary = GenericBulletinProcessor.summarize(raw_text)
                                    else:
                                        summary = GenericBulletinProcessor.summarize(raw_text)
                                    # Only add if summary is rich enough
                                    if len(summary) > 50:
                                        results.append({
                                            "source_file": os.path.basename(input_path),
                                            "identifier": entry.get('file') or entry.get('url') or identifier_hint or k or "unknown",
                                            "field": k,
                                            "summary": summary
                                        })
                                    # If the string is valid JSON, parse and extract recursively
                                    try:
                                        import json as _json
                                        parsed = _json.loads(raw_text)
                                        recursive_extract(parsed, identifier_hint=identifier_hint or k)
                                    except Exception:
                                        pass
                            elif isinstance(v, (dict, list)):
                                recursive_extract(v, identifier_hint=identifier_hint or k)
                    elif isinstance(entry, list):
                        for item in entry:
                            recursive_extract(item, identifier_hint=identifier_hint)

                # Start recursive extraction
                recursive_extract(data)

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                logger.info(f"Succès : {len(results)} résumés sauvegardés dans {output_path}")
            except Exception as e:
                logger.error(f"Erreur lors du prétraitement de {input_path} : {e}")

        # List all .json files in input_dir (non-recursive, only top-level)
        json_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]
        logger.info(f"Fichiers JSON trouvés dans {input_dir}: {json_files}")
        for fname in json_files:
            input_path = os.path.join(input_dir, fname)
            preprocessed_path = os.path.join(preprocessed_dir, f"preprocessed_{fname}")
            chunked_path = os.path.join(chunked_dir, f"chunks_{fname}")
            # 1. Preprocessing (per file)
            preprocess_single_json(input_path, preprocessed_path)
            # 2. Chunking (per file)
            if os.path.exists(preprocessed_path):
                self.chunker.chunk_preprocessed_bulletins(preprocessed_path, chunked_path)
                logger.info(f"Chunking terminé : {chunked_path}")
            else:
                logger.warning(f"Fichier prétraité manquant, chunk ignoré : {preprocessed_path}")

    def _load_raw_data(self, file_path: Path) -> Any:
        """Charge les données brutes selon l'extension."""
        ext = file_path.suffix.lower()
        with open(file_path, "r", encoding="utf-8") as f:
            if ext == ".json":
                return json.load(f)
            elif ext == ".csv":
                reader = csv.DictReader(f)
                return list(reader)
        raise ValueError(f"Extension non supportée : {ext}")

    def segment_pdf_json(self, data: List[Dict]) -> List[Dict]:
        """Traite le JSON spécifique issu d'une extraction PDF (par pages), avec nettoyage LLM Ollama."""
        docs = []
        llm_cleaner = OllamaCleaner()
        for doc in data:
            file_ref = doc.get("file") or doc.get("path") or "unknown"
            for i, page in enumerate(doc.get("pages", [])):
                content = page.get("text", "") if isinstance(page, dict) else str(page)
                if isinstance(page, dict) and "ocr_images_text" in page:
                    content += "\n" + "\n".join(page["ocr_images_text"])
                if content.strip():
                    cleaned_content = llm_cleaner.clean(content)
                    docs.append({
                        "text_content": cleaned_content,
                        "metadata": {
                            "source": file_ref,
                            "page": i + 1,
                            "type": "pdf_page"
                        },
                        "original_id": file_ref
                    })
        return self.chunker.chunk_documents(docs)
    
    def segment_csv(self, data: List[Dict]) -> List[Dict]:
        """Traite un CSV en découpant chaque ligne comme un document."""
        docs = []
        for i, row in enumerate(data):
            content = row.get("text_content") or row.get("content") or row.get("text")
            if content:
                docs.append({
                    "text_content": content,
                    "metadata": {**row, "row_index": i, "type": "csv_row"},
                    "original_id": row.get("id") or "csv_row"
                })
        return self.chunker.chunk_documents(docs)

    def segment_json(self, data: List[Dict]) -> List[Dict]:
        """Traite un JSON générique contenant des champs textuels."""
        docs = []
        for doc in data:
            content = doc.get("text_content") or doc.get("content") or doc.get("text")
            if content:
                docs.append({
                    "text_content": content,
                    "metadata": {k: v for k, v in doc.items() if k != "text_content"},
                    "original_id": doc.get("id") or doc.get("original_id") or "json_doc"
                })
        return self.chunker.chunk_documents(docs)

    def process(self, input_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Point d'entrée principal : Détecte le format, charge et segmente.
        """
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {path}")

        logger.info(f"Début de l'ingestion : {path.name}")
        data = self._load_raw_data(path)

        if path.suffix.lower() == ".csv":
            chunks = self.segment_csv(data)
        elif path.suffix.lower() == ".json":
            # Heuristique : Si on trouve une clé 'pages', c'est un PDF parsé
            if data and isinstance(data, list) and isinstance(data[0], dict) and "pages" in data[0]:
                chunks = self.segment_pdf_json(data)
            else:
                chunks = self.segment_json(data)
        
        logger.info(f"Ingestion terminée : {len(chunks)} chunks générés.")
        return chunks

# --- Interface Directe pour Pipeline ---

def ingest_file(
    input_file: str, 
    output_file: Optional[str] = None, 
    chunk_size: Optional[int] = None, 
    chunk_overlap: Optional[int] = None
) -> List[Dict]:
    """
    Fonction utilitaire pour appel direct dans un pipeline.
    """
    ingestor = GenericIngestor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = ingestor.process(input_file)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        logger.info(f"Chunks sauvegardés dans : {output_file}")
    
    return chunks


if __name__ == "__main__":
    ingestor = GenericIngestor()
    ingestor.preprocess_and_chunk(input_dir="data", preprocessed_dir="data/preprocessed", chunked_dir="data/chunked")
