from rag.components.vector_store import VectorStoreHandler
from sentence_transformers import SentenceTransformer

class EmbeddingService:
    """
    Wrapper for embedding logic, compatible with legacy imports.
    Uses SentenceTransformer for embedding text.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list:
        return self.model.encode(text, show_progress_bar=False, normalize_embeddings=True).tolist()

    @staticmethod
    def embed_batch(texts: list, model_name: str = "all-MiniLM-L6-v2") -> list:
        model = SentenceTransformer(model_name)
        return model.encode(texts, show_progress_bar=False, normalize_embeddings=True).tolist()
