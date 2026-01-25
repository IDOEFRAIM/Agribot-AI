import json
import logging
import numpy as np
import faiss
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

# --- Configuration du Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rag.VectorStore")

class VectorStoreHandler:
    def get_meteo_data(self, zone_id: str = None, k: int = 10) -> list:
        """
        Retrieve structured meteo data (t_min, t_max, rh, precip) from the vector store.
        Optionally filter by zone_id if present in metadata.
        Returns a list of dicts with available fields.
        """
        query = "weather" if not zone_id else f"weather {zone_id}"
        results = self.query_text(query_text=query, k=k)
        meteo_chunks = []
        for chunk in results:
            meteo = {}
            for key in ["t_min", "t_max", "rh", "precip", "zone_id"]:
                if key in chunk:
                    meteo[key] = chunk[key]
            # If filtering by zone, skip if zone_id doesn't match
            if zone_id and meteo.get("zone_id") != zone_id:
                continue
            if any(meteo.get(k) is not None for k in ["t_min", "t_max", "rh", "precip"]):
                meteo_chunks.append(meteo)
        return meteo_chunks

    def __init__(
        self, 
        index_path: str = "data/vector_store/agriconnect.index", 
        metadata_path: str = "data/vector_store/metadata.json", 
        dimension: int = 384
    ):
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        self.dimension = dimension
        # Initialisation des répertoires
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        # Chargement des composants
        self.metadata = self._load_metadata()
        self.index = self._init_index()

    def embed_text(self, text: str, model_name: str = "all-MiniLM-L6-v2") -> List[float]:
        """Embed a text string using SentenceTransformers."""
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        return model.encode(text, show_progress_bar=False, normalize_embeddings=True).tolist()

    def embed_and_store_chunks(self, chunked_dir: str = "data/chunked", model_name: str = "all-MiniLM-L6-v2"):
        """
        Embed all chunks from chunked_dir and store them in the FAISS vector store.
        """
        from sentence_transformers import SentenceTransformer
        import os
        model = SentenceTransformer(model_name)
        for fname in os.listdir(chunked_dir):
            if not fname.endswith('.json'):
                continue
            chunked_path = os.path.join(chunked_dir, fname)
            with open(chunked_path, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            docs_to_add = []
            for chunk in chunks:
                text = chunk.get('text_content') or chunk.get('summary') or ''
                if not text.strip():
                    continue
                vector = model.encode(text, show_progress_bar=False, normalize_embeddings=True).tolist()
                doc = {**chunk, 'vector': vector}
                docs_to_add.append(doc)
            if docs_to_add:
                print(f"Adding {len(docs_to_add)} chunks from {fname} to vector store...")
                self.add_documents(docs_to_add)
        print("All chunks embedded and added to FAISS vector store.")

    def query_text(self, query_text: str, k: int = 4, model_name: str = "all-MiniLM-L6-v2", filter_dict: Optional[Dict] = None) -> List[Dict]:
        """
        Embed the query text and retrieve top-k similar chunks.
        """
        vector = self.embed_text(query_text, model_name=model_name)
        return self.search(vector, k=k, filter_dict=filter_dict)

    """
    Gestionnaire FAISS local avec mapping d'identifiants et persistance.
    Optimisé pour la recherche sémantique (Similarité Cosine via Normalisation L2).
    """

    def _init_index(self) -> faiss.Index:
        """Charge l'index existant ou crée un nouvel index IndexIDMap2."""
        if self.index_path.exists():
            try:
                logger.info(f"Chargement de l'index FAISS : {self.index_path}")
                index = faiss.read_index(str(self.index_path))
                if not isinstance(index, faiss.IndexIDMap):
                    logger.warning("Index incompatible détecté. Re-création...")
                    return self._create_empty_index()
                return index
            except Exception as e:
                logger.error(f"Erreur de lecture d'index : {e}")
        
        return self._create_empty_index()

    def _create_empty_index(self) -> faiss.Index:
        """Crée un index FlatL2 enveloppé dans un IDMap pour la gestion des IDs."""
        logger.info(f"Création d'un nouvel index (Dim: {self.dimension})")
        quantizer = faiss.IndexFlatL2(self.dimension)
        return faiss.IndexIDMap2(quantizer)

    def _load_metadata(self) -> Dict[int, Dict[str, Any]]:
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
            except Exception as e:
                logger.error(f"Erreur métadonnées : {e}")
        return {}

    def _save(self):
        """Persiste l'index et les métadonnées sur le disque."""
        try:
            faiss.write_index(self.index, str(self.index_path))
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            logger.debug("Base vectorielle sauvegardée.")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde : {e}")

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        Ajoute des documents. Les vecteurs sont normalisés pour la similarité cosine.
        """
        if not documents: return
            
        vectors, valid_docs = [], []
        
        for doc in documents:
            vec = doc.get("vector")
            if vec is None or len(vec) != self.dimension:
                continue
            
            vectors.append(np.array(vec, dtype='float32'))
            valid_docs.append(doc)

        if not vectors: return

        # Normalisation L2 pour transformer la distance L2 en Cosine Similarity
        np_vectors = np.stack(vectors)
        faiss.normalize_L2(np_vectors)
        
        # Génération d'IDs uniques
        current_max_id = max(self.metadata.keys()) if self.metadata else -1
        ids = np.arange(current_max_id + 1, current_max_id + 1 + len(valid_docs)).astype('int64')
        
        # Ajout à FAISS
        self.index.add_with_ids(np_vectors, ids)
        
        # Mise à jour des métadonnées (sans stocker le vecteur brut pour gagner de la place)
        for i, doc in enumerate(valid_docs):
            meta = {k: v for k, v in doc.items() if k != "vector"}
            self.metadata[int(ids[i])] = meta
            
        self._save()
        logger.info(f"Ajout de {len(valid_docs)} documents. Total : {self.index.ntotal}")

    def search(self, query_vector: List[float], k: int = 4, filter_dict: Optional[Dict] = None) -> List[Dict]:
        """
        Recherche sémantique avec filtrage optionnel des métadonnées.
        """
        if self.index.ntotal == 0: return []

        # Normalisation de la requête
        np_query = np.array([query_vector], dtype='float32')
        faiss.normalize_L2(np_query)
        
        # On récupère plus de candidats si un filtre est appliqué
        search_k = k * 5 if filter_dict else k
        distances, indices = self.index.search(np_query, min(search_k, self.index.ntotal))
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1: continue
            
            meta = self.metadata.get(int(idx))
            if not meta: continue
            
            # Post-filtering logique
            if filter_dict:
                if not all(meta.get(fk) == fv for fk, fv in filter_dict.items()):
                    continue
            
            res = {**meta, "score": 1 - (float(dist) / 2)} # Conversion distance -> score de similarité
            results.append(res)
            
            if len(results) >= k: break
                
        return results

    def delete_by_metadata(self, key: str, value: Any):
        """Supprime les documents dont une métadonnée correspond à la valeur."""
        ids_to_remove = [k for k, v in self.metadata.items() if v.get(key) == value]
        
        if ids_to_remove:
            self.index.remove_ids(np.array(ids_to_remove, dtype='int64'))
            for k in ids_to_remove: del self.metadata[k]
            self._save()
            logger.info(f"Supprimé {len(ids_to_remove)} documents ({key}={value}).")