import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from rag.components.vector_store import VectorStoreHandler
from services.utils.cache import StorageManager

class VectorStorePipeline:
    """
    Encapsulates the logic for embedding and storing/retrieving chunks in the FAISS vector store.
    """
    def __init__(self, 
                 chunked_dir: str = "data/chunked", 
                 embedding_model: str = "all-MiniLM-L6-v2", 
                 vector_dim: int = 384,
                 index_path: str = "data/vector_store/agriconnect.index",
                 metadata_path: str = "data/vector_store/metadata.json"):
        self.chunked_dir = chunked_dir
        self.model = SentenceTransformer(embedding_model)
        self.vector_store = VectorStoreHandler(index_path=index_path, metadata_path=metadata_path, dimension=vector_dim)

    def embed_and_store_all(self):
        """Embed all chunks and store them in the vector store."""
        for fname in os.listdir(self.chunked_dir):
            if not fname.endswith('.json'):
                continue
            chunked_path = os.path.join(self.chunked_dir, fname)
            with open(chunked_path, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            docs_to_add = []
            for chunk in chunks:
                text = chunk.get('text_content') or chunk.get('summary') or ''
                if not text.strip():
                    continue
                vector = self.model.encode(text, show_progress_bar=False, normalize_embeddings=True).tolist()
                doc = {**chunk, 'vector': vector}
                docs_to_add.append(doc)
            if docs_to_add:
                print(f"Adding {len(docs_to_add)} chunks from {fname} to vector store...")
                self.vector_store.add_documents(docs_to_add)
        print("All chunks embedded and added to FAISS vector store.")


    def query(self, query_text: str, k: int = 4, filter_dict: Optional[Dict] = None, use_cache: bool = True, agent_role: str = "default", zone_id: str = "default", cache_ttl: int = 60) -> List[Dict]:
        """
        Embed the query and retrieve top-k similar chunks, with optional caching using StorageManager.
        """
        if use_cache:
            with StorageManager() as storage:
                cached = storage.get_agent_cache(query_text, agent_role, zone_id, ttl_minutes=cache_ttl)
                if cached is not None:
                    print("[CACHE HIT] Returning cached results.")
                    return cached
        vector = self.model.encode(query_text, show_progress_bar=False, normalize_embeddings=True).tolist()
        results = self.vector_store.search(vector, k=k, filter_dict=filter_dict)
        if use_cache:
            with StorageManager() as storage:
                storage.set_agent_cache(query_text, agent_role, zone_id, results)
        return results

# Example usage:
# pipeline = VectorStorePipeline()
# pipeline.embed_and_store_all()
# results = pipeline.query("climat Burkina Faso", k=5, use_cache=True)
# for r in results:
#     print(r)
