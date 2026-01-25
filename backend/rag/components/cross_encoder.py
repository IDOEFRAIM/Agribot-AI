import math
import logging
import numpy as np
from typing import List, Tuple, Dict, Any
from sentence_transformers import CrossEncoder as STCrossEncoder

# --- Configuration du Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag.CrossEncoder")

class RAGCrossEncoder:
    """
    Gestionnaire de Re-ranking pour pipeline RAG.
    Utilise un modèle Cross-Encoder pour affiner les résultats de recherche FAISS.
    """
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(
        self, 
        model_name: str = DEFAULT_MODEL, 
        device: str = "cpu", 
        batch_size: int = 32, 
        temperature: float = 1.0
    ):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.temperature = max(1e-6, float(temperature)) # Evite la division par zéro
        
        try:
            self.model = STCrossEncoder(self.model_name, device=self.device)
            logger.info(f"✅ CrossEncoder chargé : {self.model_name} sur {self.device}")
        except Exception as e:
            logger.error(f"❌ Erreur critique chargement CrossEncoder : {e}")
            raise RuntimeError(f"Impossible de charger le modèle : {self.model_name}")

    def _sigmoid(self, score: float) -> float:
        """Transforme le logit brut en probabilité (score entre 0 et 1)."""
        try:
            return 1.0 / (1.0 + math.exp(-score / self.temperature))
        except OverflowError:
            return 1.0 if score > 0 else 0.0

    def rank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Réordonne une liste de documents selon leur pertinence réelle avec la requête.
        """
        if not documents:
            return []

        # Préparation des paires (Query, Document)
        pairs = [(query, doc.get("text_content", "")) for doc in documents]
        
        # Prédiction des scores (logits)
        logger.debug(f"Calcul des scores Cross-Encoder pour {len(pairs)} paires...")
        logits = self.model.predict(
            pairs, 
            batch_size=self.batch_size, 
            show_progress_bar=False
        )

        # Application du sigmoid et mise à jour des documents
        reranked_docs = []
        for i, logit in enumerate(logits):
            doc = documents[i].copy()
            doc["rerank_score"] = self._sigmoid(float(logit))
            reranked_docs.append(doc)

        # Tri par score décroissant
        reranked_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        
        return reranked_docs[:top_k]

# --- Exemple d'utilisation dans ton pipeline ---
# results = vector_store.search(query_vec, k=20) # Etape 1 : Retrieval (Rapide)
# final_docs = cross_encoder.rank(query_text, results, top_k=5) # Etape 2 : Re-ranking (Précis)