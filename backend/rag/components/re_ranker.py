import logging
import numpy as np
from typing import List, Dict, Any, Optional
from rag.components.cross_encoder import RAGCrossEncoder

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag.Reranker")

ROLE_PROFILES = {
    "CROP": {
        "keywords": {"culture": 0.2, "maïs": 0.3, "semis": 0.2, "récolte": 0.3, "rendement": 0.2, "variété": 0.2},
        "boost_factor": 0.20, 
        "weights": (0.40, 0.60)  # (Poids FAISS, Poids Cross-Encoder)
    },
    "SOIL": {
        "keywords": {"sol": 0.3, "fertilité": 0.3, "argileux": 0.2, "engrais": 0.2, "nutriments": 0.2, "NPK": 0.3},
        "boost_factor": 0.25, 
        "weights": (0.35, 0.65)
    },
    "METEO": {
        "keywords": {"pluie": 0.3, "pluviométrie": 0.3, "prévisions": 0.2, "sécheresse": 0.3, "vent": 0.2},
        "boost_factor": 0.15, 
        "weights": (0.45, 0.55)
    },
    "MARKET": {
        "keywords": {"prix": 0.3, "marché": 0.3, "vente": 0.2, "acheteur": 0.2, "grossiste": 0.2, "fcfa": 0.3},
        "boost_factor": 0.30, 
        "weights": (0.30, 0.70)
    },
    "HEALTH": {
        "keywords": {"maladie": 0.3, "ravageur": 0.3, "chenille": 0.3, "traitement": 0.2, "symptôme": 0.2},
        "boost_factor": 0.25, 
        "weights": (0.35, 0.65)
    }
}

class HybridReranker:
    """
    Reranker hybride pour AgriConnect.
    Combine Retrieval Vectoriel (FAISS), Re-ranking Sémantique (Cross-Encoder)
    et Boost Lexical contextuel par domaine d'expertise.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.encoder = RAGCrossEncoder(model_name=model_name) if model_name else RAGCrossEncoder()
        logger.info("⚖️ Reranker hybride AgriConnect initialisé.")

    def _normalize_scores(self, scores: List[float], invert: bool = False) -> np.ndarray:
        """Normalise une liste de scores entre 0 et 1."""
        arr = np.array(scores, dtype=np.float32)
        s_min, s_max = arr.min(), arr.max()
        
        if s_max == s_min:
            return np.ones_like(arr)
        
        norm = (arr - s_min) / (s_max - s_min)
        return (1.0 - norm) if invert else norm

    def rerank(self, documents: List[Dict[str, Any]], query: str, agent_role: str) -> List[Dict[str, Any]]:
        """
        Réordonne les documents avec une logique hybride : 
        Score Final = (w1*Norm_FAISS + w2*Norm_CE) * Boost_Lexical
        """
        if not documents:
            return []

        profile = ROLE_PROFILES.get(agent_role, {
            "keywords": {}, "boost_factor": 0.0, "weights": (0.5, 0.5)
        })

        # 1. Calcul des scores Cross-Encoder (Sémantique profonde)
        pairs = [(query, doc.get("text_content", "")) for doc in documents]
        try:
            ce_raw_scores = self.encoder.model.predict(pairs, batch_size=16, show_progress_bar=False)
        except Exception as e:
            logger.error(f"Erreur Cross-Encoder : {e}. Fallback sur FAISS pur.")
            return sorted(documents, key=lambda x: x.get('score', 0), reverse=True)

        # 2. Normalisation des deux sources
        # FAISS (Distance L2) : plus petit est mieux -> on inverse
        norm_faiss = self._normalize_scores([doc.get('score', 1.0) for doc in documents], invert=True)
        # Cross-Encoder (Logits) : plus grand est mieux
        norm_ce = self._normalize_scores(ce_raw_scores)

        # 3. Calcul du boost lexical et du score final
        w_faiss, w_ce = profile["weights"]
        boost_config = profile["keywords"]
        boost_mult = profile["boost_factor"]

        reranked_results = []
        for i, doc in enumerate(documents):
            # Calcul du boost lexical métier
            text_lower = doc.get("text_content", "").lower()
            lexical_weight = sum(weight for kw, weight in boost_config.items() if kw.lower() in text_lower)
            actual_boost = 1.0 + min(lexical_weight * boost_mult, 0.4) # Plafond à +40%

            # Score pondéré
            hybrid_score = (w_faiss * norm_faiss[i] + w_ce * norm_ce[i]) * actual_boost
            
            # Enrichissement du document
            new_doc = doc.copy()
            new_doc["final_score"] = float(hybrid_score)
            new_doc["metadata"] = {
                **(new_doc.get("metadata", {})),
                "debug_info": {
                    "norm_faiss": round(float(norm_faiss[i]), 3),
                    "norm_ce": round(float(norm_ce[i]), 3),
                    "lexical_boost": round(actual_boost, 2)
                }
            }
            reranked_results.append(new_doc)

        # Tri final par score décroissant
        reranked_results.sort(key=lambda x: x["final_score"], reverse=True)
        logger.info(f"Reranking terminé pour le rôle {agent_role}.")
        
        return reranked_results

# Alias for compatibility with older imports
Reranker = HybridReranker