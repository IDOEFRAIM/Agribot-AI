"""
MCP RAG Server — Accès standardisé à la base de connaissances agronomiques.
===========================================================================

AVANT (couplage direct) :
    retriever = AgileRetriever()
    nodes = retriever.search(query, profile="debutant")

APRÈS (découplé via MCP) :
    result = mcp_rag.call_tool("search_agronomy_docs", {
        "query": "traitement rouille blé",
        "region": "Burkina",
        "level": "debutant"
    })

AVANTAGE : Si on migre de FAISS vers Pinecone, Chroma, ou Weaviate,
on ne touche QUE ce fichier. Les agents ne changent pas.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MCP.RAG")


class MCPRagServer:
    """
    Serveur MCP exposant le RAG comme un outil standardisé.
    
    Outils exposés :
      - search_agronomy_docs(query, region, level, top_k)
        → Recherche dans la base documentaire agronomique (HyDe + reranking)
      
      - get_doc_sources(query)
        → Retourne les sources utilisées (traçabilité)
    
    Ressources exposées :
      - agri://rag/stats → Statistiques du corpus (nombre docs, dernière mise à jour)
    """

    def __init__(self, retriever=None):
        """
        Args:
            retriever: Instance AgileRetriever existante (réutilisée, pas recréée)
        """
        self._retriever = retriever
        self._tools = {}
        self._resources = {}
        self._register_tools()
        self._register_resources()
        logger.info("🔌 MCP RAG Server initialisé")

    def _lazy_retriever(self):
        """Initialisation paresseuse du retriever (coûteux en mémoire)."""
        if self._retriever is None:
            try:
                from backend.rag.retriever import AgileRetriever
                self._retriever = AgileRetriever()
                logger.info("📚 RAG retriever chargé (lazy init)")
            except Exception as e:
                logger.error("RAG retriever unavailable: %s", e)
        return self._retriever

    # ═══════════════════════════════════════════════════════════
    # REGISTRATION
    # ═══════════════════════════════════════════════════════════

    def _register_tools(self):
        self._tools = {
            "search_agronomy_docs": {
                "name": "search_agronomy_docs",
                "description": (
                    "Recherche dans la base de connaissances agronomiques "
                    "d'Afrique de l'Ouest (Burkina Faso, Sahel). "
                    "Utilise HyDe + reranking pour une pertinence maximale."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Question agronomique"},
                        "region": {"type": "string", "description": "Région (ex: Burkina, Sahel)", "default": "Burkina"},
                        "level": {
                            "type": "string",
                            "description": "Niveau de l'agriculteur",
                            "enum": ["debutant", "intermediaire", "expert"],
                            "default": "debutant",
                        },
                        "top_k": {"type": "integer", "description": "Nombre de résultats", "default": 3},
                    },
                    "required": ["query"],
                },
                "handler": self._search_docs,
            },
            "get_doc_sources": {
                "name": "get_doc_sources",
                "description": "Retourne les sources documentaires utilisées pour une recherche (traçabilité)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
                "handler": self._get_sources,
            },
        }

    def _register_resources(self):
        self._resources = {
            "agri://rag/stats": {
                "name": "RAG Statistics",
                "description": "Statistiques du corpus documentaire",
                "mime_type": "application/json",
                "handler": self._read_stats,
            },
        }

    # ═══════════════════════════════════════════════════════════
    # INTERFACE MCP
    # ═══════════════════════════════════════════════════════════

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
            for t in self._tools.values()
        ]

    def list_resources(self) -> List[Dict[str, Any]]:
        return [
            {"uri": uri, "name": r["name"], "description": r["description"], "mimeType": r["mime_type"]}
            for uri, r in self._resources.items()
        ]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Outil RAG inconnu: {name}", "status": "not_found"}
        try:
            result = tool["handler"](arguments)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "status": "ok",
            }
        except Exception as e:
            logger.error("MCP RAG call_tool error (%s): %s", name, e)
            return {"error": str(e), "status": "error"}

    def read_resource(self, uri: str, params: Dict = None) -> Dict[str, Any]:
        resource = self._resources.get(uri)
        if not resource:
            return {"error": f"Ressource RAG inconnue: {uri}", "status": "not_found"}
        try:
            data = resource["handler"](params or {})
            return {
                "contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False)}],
                "status": "ok",
            }
        except Exception as e:
            return {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════════════════════
    # HANDLERS
    # ═══════════════════════════════════════════════════════════

    def _search_docs(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Recherche agronomique via HyDe + reranking."""
        retriever = self._lazy_retriever()
        if not retriever:
            return {"context": "", "sources": [], "error": "RAG indisponible"}

        query = arguments["query"]
        level = arguments.get("level", "debutant")
        top_k = arguments.get("top_k", 3)

        # Adapter le ton HyDe au niveau utilisateur
        tone_map = {"debutant": "simple", "intermediaire": "standard", "expert": "technique"}
        tone = tone_map.get(level, "standard")

        try:
            # 1. HyDe : génère un document hypothétique
            hyde_doc = retriever.generate_hyde_doc(query, tone=tone)

            # 2. Recherche vectorielle
            from llama_index.core import QueryBundle
            query_bundle = QueryBundle(query_str=hyde_doc)

            if retriever.vector_retriever:
                nodes = retriever.vector_retriever.retrieve(query_bundle)
            else:
                nodes = []

            # 3. Reranking
            nodes = retriever.rerank(query, nodes, top_k=top_k)

            # 4. Formatage des résultats
            context_parts = []
            sources = []
            for i, node in enumerate(nodes):
                text = node.node.get_content() if hasattr(node, "node") else str(node)
                meta = node.node.metadata if hasattr(node, "node") else {}
                context_parts.append(f"[Doc {i+1}] {text[:500]}")
                sources.append({
                    "rank": i + 1,
                    "source": meta.get("source", "Inconnu"),
                    "type": meta.get("type", "Document"),
                    "score": round(node.score, 4) if node.score else None,
                })

            return {
                "context": "\n\n".join(context_parts),
                "sources": sources,
                "query_used": query,
                "hyde_active": True,
                "results_count": len(nodes),
            }

        except Exception as e:
            logger.error("RAG search error: %s", e)
            return {"context": "", "sources": [], "error": str(e)}

    def _get_sources(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Retourne les sources documentaires pour traçabilité."""
        result = self._search_docs(arguments)
        return {"sources": result.get("sources", []), "query": arguments.get("query")}

    def _read_stats(self, params: Dict) -> Dict[str, Any]:
        """Statistiques du corpus RAG."""
        retriever = self._lazy_retriever()
        stats = {"status": "unknown", "total_docs": 0}
        if retriever and retriever.index:
            try:
                if hasattr(retriever.index, "_vector_store") and hasattr(retriever.index._vector_store, "client"):
                    stats["total_docs"] = retriever.index._vector_store.client.ntotal
                    stats["status"] = "ready"
                else:
                    stats["status"] = "ready"
            except Exception:
                stats["status"] = "error"
        else:
            stats["status"] = "unavailable"
        return stats
