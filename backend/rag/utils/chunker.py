from typing import List, Dict, Any, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
import json
import re
from pathlib import Path
from collections import defaultdict

class Chunker:
    """
    Chunker optimisé pour pipeline RAG.
    - Gère le découpage récursif intelligent.
    - Préserve l'intégrité des métadonnées.
    - Génère des IDs de chunks traçables.
    """
    def __init__(self, max_tokens=200, chunk_size: int = 500, chunk_overlap: int = 50):
        self.max_tokens = max_tokens
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ".", "!", "?", " ", ""]
        )

    @staticmethod
    def normalize_zone(zone):
        # Corrige les encodages et harmonise les noms de zones
        mapping = {
            'D�dougou': 'Dédougou',
            'P�': 'Pô',
        }
        return mapping.get(zone, zone)

    @staticmethod
    def clean_text(text):
        # Nettoie les caractères spéciaux, espaces, doublons
        text = text.replace('\u2019', "'").replace('\u2013', '-').replace('\u00e9', 'é')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def split_by_tokens(self, text):
        # Découpe le texte en sous-chunks si trop long (approx. 1 token ≈ 4 chars)
        words = text.split()
        chunk_size = self.max_tokens * 4
        for i in range(0, len(words), chunk_size):
            yield ' '.join(words[i:i+chunk_size])

    @staticmethod
    def synthesize_intro(zone, texts, default_label="Synthèse indisponible"):
        # Génère une intro synthétique à partir des phrases clés
        if not texts:
            return f"{default_label} pour {zone}."
        # Cherche une phrase qui résume le climat ou la thématique
        for t in texts:
            m = re.search(r'(climat|températures|saison|année)[^.!?]*[.!?]', t, re.IGNORECASE)
            if m:
                return f"{zone} : {m.group(0).strip()}"
        # Fallback : première phrase
        return f"{zone} : {texts[0][:120]}..."

    def chunk_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Découpe une liste de dictionnaires en chunks.
        Chaque chunk conserve ses métadonnées et reçoit un ID unique indexé.
        """
        chunked_output = []

        for doc in documents:
            # Récupération du texte source
            source_text = doc.get("text_content") or doc.get("content") or doc.get("text") or ""
            if not source_text.strip():
                continue

            # Identification de la source pour le traçage
            original_id = doc.get("original_id") or doc.get("id") or doc.get("file") or "unknown"
            
            # Extraction des métadonnées (on exclut les champs de texte brut)
            metadata_base = {
                k: v for k, v in doc.items() 
                if k not in ["text_content", "content", "text", "chunk"]
            }

            # Découpage effectif
            chunks = self.splitter.split_text(source_text)

            for i, chunk_content in enumerate(chunks):
                chunked_output.append({
                    "chunk_id": f"{original_id}_v{i}",
                    "text_content": chunk_content,
                    "original_id": original_id,
                    "metadata": {
                        **metadata_base,
                        "chunk_index": i,
                        "total_chunks": len(chunks)
                    }
                })

        return chunked_output

    def chunk_meteo_by_zone(self, input_path, output_path):
        """
        Regroupe, nettoie, synthétise et découpe les textes météo par zone.
        Chaque chunk contient une vraie synthèse + détails, découpé si trop long.
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        zone_chunks = defaultdict(list)
        zone_meteo_fields = defaultdict(dict)
        for v in data.values() if isinstance(data, dict) else data:
            if v.get('source_type') == 'METEO_VECTOR':
                zone = self.normalize_zone(v.get('zone_id', 'Unknown'))
                txt = self.clean_text(v.get('text_content', ''))
                # Extract meteo fields if present
                for key in ["t_min", "t_max", "rh", "precip"]:
                    if key in v:
                        zone_meteo_fields[zone][key] = v[key]
                if txt and txt not in zone_chunks[zone]:
                    zone_chunks[zone].append(txt)

        new_chunks = []
        for zone, texts in zone_chunks.items():
            full_text = ' '.join(texts)
            intro = self.synthesize_intro(zone, texts, default_label="Climat")
            meteo_fields = zone_meteo_fields.get(zone, {})
            for i, chunk_text in enumerate(self.split_by_tokens(full_text)):
                chunk = {
                    'zone_id': zone,
                    'source_type': 'METEO_VECTOR',
                    'title': f'Climat annuel de {zone}' + (f' (part {i+1})' if i > 0 else ''),
                    'text_content': intro + '\n' + chunk_text,
                    'metadata': {
                        'zone': zone,
                        'chunk_index': i,
                        'source': 'meteoburkina.bf',
                    },
                    # Add meteo fields to chunk
                    **meteo_fields
                }
                new_chunks.append(chunk)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(new_chunks, f, ensure_ascii=False, indent=2)

    def chunk_pdf_pages(self, input_path, output_path):
        """
        Regroupe, nettoie, synthétise et découpe les bulletins PDF extraits par fichier.
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        file_chunks = defaultdict(list)
        for v in data:
            file = v.get('file', 'Unknown')
            txt = self.clean_text(v.get('text_content', ''))
            if txt and txt not in file_chunks[file]:
                file_chunks[file].append(txt)

        new_chunks = []
        for file, texts in file_chunks.items():
            full_text = ' '.join(texts)
            intro = self.synthesize_intro(file, texts, default_label="Synthèse bulletin")
            for i, chunk_text in enumerate(self.split_by_tokens(full_text)):
                chunk = {
                    'file': file,
                    'source_type': 'PDF_BULLETIN',
                    'title': f'Bulletin {file}' + (f' (part {i+1})' if i > 0 else ''),
                    'text_content': intro + '\n' + chunk_text,
                    'metadata': {
                        'file': file,
                        'chunk_index': i,
                        'source': 'pdf',
                    }
                }
                new_chunks.append(chunk)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(new_chunks, f, ensure_ascii=False, indent=2)

    def chunk_preprocessed_bulletins(self, input_path, output_path):
        """
        Découpe les résumés synthétiques du fichier preprocessed_bulletins.json en chunks.
        Chaque chunk conserve la source et l'identifiant d'origine.
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        chunked_output = []
        for entry in data:
            summary = entry.get('summary', '')
            if not summary.strip():
                continue
            source_file = entry.get('source_file', 'unknown')
            identifier = entry.get('identifier', 'unknown')
            processed_at = entry.get('processed_at', '')
            # Découpage du résumé en chunks
            chunks = self.splitter.split_text(summary)
            for i, chunk_content in enumerate(chunks):
                chunked_output.append({
                    'chunk_id': f"{identifier}_v{i}",
                    'text_content': chunk_content,
                    'source_file': source_file,
                    'identifier': identifier,
                    'processed_at': processed_at,
                    'metadata': {
                        'chunk_index': i,
                        'total_chunks': len(chunks)
                    }
                })

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(chunked_output, f, ensure_ascii=False, indent=2)

# --- EXEMPLE D'UTILISATION ---
# chunker = Chunker(max_tokens=200)
# chunker.chunk_meteo_by_zone('data/vector_store/metadata.json', 'data/vector_store/chunks_meteo_synthetiques.json')
# chunker.chunk_pdf_pages('data/all_pdfs_chunks.json', 'data/chunks_pdf_synthetiques.json')
# chunker.chunk_preprocessed_bulletins('data/preprocessed_bulletins.json', 'data/chunks_bulletins.json')