"""
MCP Context Server — ContextOptimizer exposé comme MCP Host.
==============================================================

C'est le POINT D'ENTRÉE UNIVERSEL pour tout protocole (A2A, ACP, AG-UI)
qui a besoin du contexte utilisateur standardisé.

AVANT (couplage) :
    optimizer = ContextOptimizer(...)
    context = optimizer.build_context(user_id, query)

APRÈS (standardisé MCP) :
    result = mcp_context.call_tool("build_context", {
        "user_id": "...", "query": "...", "zone": "bobo"
    })

Tout agent (interne ou externe via A2A/ACP) peut consommer
les mêmes données de contexte de manière standardisée.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger("MCP.Context")


class MCPContextServer:
    """
    MCP Host — Point d'accès universel au contexte utilisateur.
    
    Outils :
      - build_context(user_id, query, zone, crop)  → Contexte optimisé complet
      - get_token_budget()                          → Budget tokens par composant
    
    Ressources :
      - agri://context/{user_id}  → Contexte courant mis en cache
    """

    def __init__(self, context_optimizer=None, session_factory=None, llm_client=None):
        """
        Args:
            context_optimizer: Instance ContextOptimizer existante
            session_factory: Factory SQLAlchemy (si optimizer non fourni)
            llm_client: Client LLM (si optimizer non fourni)
        """
        self._optimizer = context_optimizer
        self._session_factory = session_factory
        self._llm = llm_client
        self._context_cache = {}  # Cache léger par user_id
        self._tools = {}
        self._resources = {}
        self._register_tools()
        self._register_resources()
        logger.info("🔌 MCP Context Server (Host) initialisé")

    def _lazy_optimizer(self):
        """Initialisation paresseuse du ContextOptimizer."""
        if self._optimizer is None and self._session_factory:
            try:
                from backend.services.memory import (
                    UserFarmProfile, EpisodicMemory, ProfileExtractor, ContextOptimizer,
                )
                _profile = UserFarmProfile(self._session_factory)
                _episodic = EpisodicMemory(self._session_factory, llm_client=self._llm)
                _extractor = ProfileExtractor(self._llm, _profile)
                self._optimizer = ContextOptimizer(_profile, _episodic, _extractor)
                logger.info("🧠 ContextOptimizer chargé (lazy init)")
            except Exception as e:
                logger.error("ContextOptimizer unavailable: %s", e)
        return self._optimizer

    # ═══════════════════════════════════════════════════════════
    # REGISTRATION
    # ═══════════════════════════════════════════════════════════

    def _register_tools(self):
        self._tools = {
            "build_context": {
                "name": "build_context",
                "description": (
                    "Construit le contexte utilisateur optimisé pour un agent. "
                    "Combine profil structuré (~80 tokens) + épisodes pertinents (~120 tokens) + "
                    "métadonnées. Remplace 5000 tokens d'historique brut par ~350 tokens ciblés."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "Identifiant de l'agriculteur"},
                        "query": {"type": "string", "description": "Question courante de l'agriculteur"},
                        "zone": {"type": "string", "description": "Zone géographique (optionnel)"},
                        "crop": {"type": "string", "description": "Culture concernée (optionnel)"},
                    },
                    "required": ["user_id", "query"],
                },
                "handler": self._build_context,
            },
            "get_token_budget": {
                "name": "get_token_budget",
                "description": "Retourne le budget tokens par composant du contexte",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
                "handler": self._get_token_budget,
            },
            "enrich_state": {
                "name": "enrich_state",
                "description": "Enrichit un état GlobalAgriState avec le contexte mémoire",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "state": {"type": "object", "description": "État de l'orchestrateur à enrichir"},
                    },
                    "required": ["state"],
                },
                "handler": self._enrich_state,
            },
            "record_interaction": {
                "name": "record_interaction",
                "description": "Enregistre une interaction dans la mémoire épisodique",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "query": {"type": "string"},
                        "response": {"type": "string"},
                        "agent": {"type": "string"},
                        "intent": {"type": "string"},
                    },
                    "required": ["user_id", "query", "response", "agent"],
                },
                "handler": self._record_interaction,
            },
        }

    def _register_resources(self):
        self._resources = {
            "agri://context/{user_id}": {
                "name": "Contexte Utilisateur",
                "description": "Contexte optimisé mis en cache pour l'utilisateur",
                "mime_type": "application/json",
                "handler": self._read_cached_context,
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
            return {"error": f"Outil Context inconnu: {name}", "status": "not_found"}
        try:
            result = tool["handler"](arguments)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
                "status": "ok",
            }
        except Exception as e:
            logger.error("MCP Context call_tool error (%s): %s", name, e)
            return {"error": str(e), "status": "error"}

    def read_resource(self, uri: str, params: Dict = None) -> Dict[str, Any]:
        for pattern, resource in self._resources.items():
            if self._uri_matches(pattern, uri):
                try:
                    data = resource["handler"](params or self._extract_params(uri))
                    return {
                        "contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False, default=str)}],
                        "status": "ok",
                    }
                except Exception as e:
                    return {"error": str(e), "status": "error"}
        return {"error": f"Ressource Context inconnue: {uri}", "status": "not_found"}

    # ═══════════════════════════════════════════════════════════
    # HANDLERS
    # ═══════════════════════════════════════════════════════════

    def _build_context(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Construit et cache le contexte optimisé."""
        optimizer = self._lazy_optimizer()
        if not optimizer:
            return {"error": "ContextOptimizer indisponible", "combined_context": "", "token_estimate": 0}

        user_id = arguments["user_id"]
        query = arguments["query"]
        zone = arguments.get("zone")
        crop = arguments.get("crop")

        result = optimizer.build_context(user_id, query, zone=zone, crop=crop)

        # Mise en cache
        self._context_cache[user_id] = result
        return result

    def _get_token_budget(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Retourne le budget tokens."""
        from backend.services.memory.context_optimizer import TOKEN_BUDGETS
        return TOKEN_BUDGETS

    def _enrich_state(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Enrichit un état avec le contexte mémoire."""
        optimizer = self._lazy_optimizer()
        if not optimizer:
            return arguments.get("state", {})

        state = arguments["state"]
        try:
            enriched = optimizer.enrich_state(state)
            return enriched
        except Exception as e:
            logger.warning("Enrich state failed: %s", e)
            return state

    def _record_interaction(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Enregistre une interaction dans la mémoire épisodique."""
        optimizer = self._lazy_optimizer()
        if not optimizer:
            return {"status": "skipped", "reason": "ContextOptimizer indisponible"}

        try:
            optimizer.record_interaction(
                user_id=arguments["user_id"],
                query=arguments["query"],
                response=arguments["response"],
                agent=arguments["agent"],
                intent=arguments.get("intent", "UNKNOWN"),
            )
            return {"status": "recorded"}
        except Exception as e:
            logger.warning("Record interaction failed: %s", e)
            return {"status": "error", "reason": str(e)}

    def _read_cached_context(self, params: Dict) -> Dict[str, Any]:
        """Lit le contexte en cache pour un utilisateur."""
        user_id = params.get("user_id")
        if user_id and user_id in self._context_cache:
            return self._context_cache[user_id]
        return {"user_id": user_id, "cached": False, "note": "Aucun contexte en cache. Utilisez build_context d'abord."}

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _uri_matches(self, pattern: str, uri: str) -> bool:
        import re
        regex = pattern.replace("{user_id}", r"[^/]+")
        return bool(re.match(regex, uri))

    def _extract_params(self, uri: str) -> Dict[str, str]:
        parts = uri.replace("agri://context/", "").split("/")
        return {"user_id": parts[0]} if parts else {}

    # ═══════════════════════════════════════════════════════════
    # CONVENIENCE (interface directe pour agents internes)
    # ═══════════════════════════════════════════════════════════

    def read_user_context(self, user_id: str, query: str = "", zone: str = "", crop: str = "") -> Dict[str, Any]:
        """
        Raccourci pour les agents internes.
        Retourne le profil/contexte utilisateur ou INSUFFICIENT_CONTEXT si incomplet.
        """
        # Vérifier d'abord le cache
        if user_id and user_id in self._context_cache:
            return self._context_cache[user_id]

        # Construire le contexte
        result = self._build_context({
            "user_id": user_id or "anonymous",
            "query": query,
            "zone": zone,
            "crop": crop,
        })
        if result.get("error"):
            return {"user_id": user_id, "cached": False}
        return result

    def check_required_fields(self, context: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
        """
        Context Elicitation — Vérifie que les champs requis sont présents.
        Retourne {"status": "ok"} ou {"error": "INSUFFICIENT_CONTEXT", "missing": [...]}.
        """
        missing = [f for f in required if not context.get(f)]
        if missing:
            return {"error": "INSUFFICIENT_CONTEXT", "missing": missing}
        return {"status": "ok"}
