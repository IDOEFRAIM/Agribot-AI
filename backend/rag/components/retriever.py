import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

# --- Configuration du Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag.Retriever")

class AgentRetriever:
    """
    Orchestrateur du Retrieval AgriConnect.
    Gère le flux : Requête -> Embedding -> FAISS -> Reranking -> Contexte final.
    """
    
    def __init__(
        self, 
        vector_store,  # VectorStoreHandler
        embedder,      # SBERT / OpenAI Embedding service
        reranker=None, # HybridReranker (optionnel mais recommandé)
        storage=None   # Cache/SQL Manager (optionnel)
    ):
        self.store = vector_store
        self.embedder = embedder
        self.reranker = reranker
        self.storage = storage
        logger.info("📡 AgentRetriever initialisé et prêt pour le dispatching.")

    def _get_query_vector(self, query: str) -> List[float]:
        """Transforme le texte en vecteur via l'embedder."""
        # On suppose que l'embedder a une méthode encode()
        return self.embedder.encode(query)

    def retrieve(
        self, 
        query: str, 
        agent_role: str = "Coordinateur", 
        limit: int = 5,
        zone: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Point d'entrée principal pour les agents de la plateforme.
        """
        logger.info(f"🔎 Retrieval pour [{agent_role}] | Zone: {zone or 'Nationale'} | Query: {query}")

        # --- ÉTAPE 1 : FAST PATH (CACHE) ---
        if self.storage:
            cache_hit = self.storage.check_cache(query, agent_role, zone)
            if cache_hit:
                logger.info("🚀 Réponse servie depuis le cache.")
                return cache_hit

        # --- ÉTAPE 2 : DEEP PATH (VECTOR SEARCH) ---
        try:
            # A. Vectorisation
            query_vec = self._get_query_vector(query)

            # B. Premier tri FAISS (on récupère 3x plus de docs pour le reranker)
            search_limit = limit * 4 if self.reranker else limit
            
            # On applique un filtre par zone si présent dans les métadonnées
            # TEMP: Désactive le filtrage par zone pour tester la récupération météo
            filter_dict = None
            
            initial_docs = self.store.search(
                query_vector=query_vec, 
                k=search_limit,
                filter_dict=filter_dict
            )

            if not initial_docs:
                logger.warning("⚠️ Aucun document trouvé dans la base vectorielle.")
                return []

            # --- ÉTAPE 3 : RERANKING (INTELLIGENCE MÉTIER) ---
            if self.reranker:
                logger.info(f"⚖️ Application du Re-ranking hybride ({len(initial_docs)} docs)...")
                final_docs = self.reranker.rerank(
                    documents=initial_docs,
                    query=query,
                    agent_role=agent_role
                )
                results = final_docs[:limit]
            else:
                results = initial_docs[:limit]

            # --- ÉTAPE 4 : FORMATAGE POUR LE LLM ---
            formatted_results = self._format_results(results)

            # Mise en cache pour les futures requêtes identiques
            if self.storage and formatted_results:
                self.storage.update_cache(query, agent_role, zone, formatted_results)

            return formatted_results

        except Exception as e:
            logger.error(f"❌ Erreur critique lors du retrieval : {e}")
            return []

    def _format_results(self, docs: List[Dict]) -> List[Dict]:
        """Nettoie et structure les résultats pour qu'ils soient digestes par l'Agent LLM."""
        formatted = []
        for d in docs:
            # Les champs sont directement dans d (pas dans 'metadata')
            formatted.append({
                "content": d.get("text_content", d.get("summary", "")),
                "source": d.get("file_name") or d.get("url") or "Source interne",
                "relevance_score": round(d.get("final_score", d.get("score", 0)), 3),
                "date": d.get("date") or d.get("created_at") or "Date inconnue",
                "zone": d.get("zone_id", "Burkina Faso")
            })
        return formatted

# --- Architecture Technique ---