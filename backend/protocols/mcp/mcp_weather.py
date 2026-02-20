"""
MCP Weather Server — Accès standardisé aux données météo et alertes.
=====================================================================

AVANT (couplage direct) :
    from backend.tools.sentinelle import SentinelleTool
    tool = SentinelleTool()
    weather = tool.get_current_conditions("bobo-dioulasso")

APRÈS (découplé via MCP) :
    result = mcp_weather.call_tool("get_weather", {"location": "bobo-dioulasso"})

AVANTAGE : Si on change de fournisseur météo (OpenWeather → ANAM → Météo-France),
on ne touche QUE ce fichier. Les agents ne changent pas.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger("MCP.Weather")


class MCPWeatherServer:
    """
    Serveur MCP exposant les données météo comme outils standardisés.
    
    Outils exposés :
      - get_weather(location)       → Conditions actuelles
      - get_forecast(location, days)  → Prévisions N jours
      - get_alerts(zone)            → Alertes climatiques actives
      - get_flood_risk(location)    → Risque inondation
      - get_satellite_data(location) → Données satellites (NDVI, EVI)
    
    Ressources exposées :
      - agri://weather/current/{location}  → Données météo en temps réel
      - agri://weather/alerts/{zone}       → Alertes actives par zone
    """

    def __init__(self, sentinelle_tool=None, llm_client=None):
        """
        Args:
            sentinelle_tool: Instance SentinelleTool existante
            llm_client: Client LLM pour les analyses avancées
        """
        self._tool = sentinelle_tool
        self._llm = llm_client
        self._tools = {}
        self._resources = {}
        self._register_tools()
        self._register_resources()
        logger.info("🔌 MCP Weather Server initialisé")

    def _lazy_tool(self):
        """Initialisation paresseuse de SentinelleTool."""
        if self._tool is None:
            try:
                from backend.tools.sentinelle import SentinelleTool
                self._tool = SentinelleTool(llm_client=self._llm)
                logger.info("🌦️ SentinelleTool chargé (lazy init)")
            except Exception as e:
                logger.error("SentinelleTool unavailable: %s", e)
        return self._tool

    # ═══════════════════════════════════════════════════════════
    # REGISTRATION
    # ═══════════════════════════════════════════════════════════

    def _register_tools(self):
        self._tools = {
            "get_weather": {
                "name": "get_weather",
                "description": "Obtient les conditions météo actuelles pour une localisation au Burkina Faso",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "Ville ou zone (ex: bobo-dioulasso, ouagadougou)"},
                    },
                    "required": ["location"],
                },
                "handler": self._get_weather,
            },
            "get_forecast": {
                "name": "get_forecast",
                "description": "Prévisions météo pour les prochains jours",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "days": {"type": "integer", "default": 3, "description": "Nombre de jours de prévision"},
                    },
                    "required": ["location"],
                },
                "handler": self._get_forecast,
            },
            "get_alerts": {
                "name": "get_alerts",
                "description": "Alertes climatiques actives (sécheresse, inondation, canicule, invasion acridienne)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "zone": {"type": "string", "description": "Zone ou région"},
                    },
                    "required": ["zone"],
                },
                "handler": self._get_alerts,
            },
            "get_flood_risk": {
                "name": "get_flood_risk",
                "description": "Évaluation du risque d'inondation pour une zone",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                    },
                    "required": ["location"],
                },
                "handler": self._get_flood_risk,
            },
            "get_satellite_data": {
                "name": "get_satellite_data",
                "description": "Données satellites de végétation (NDVI, EVI) pour suivi des cultures",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                    },
                    "required": ["location"],
                },
                "handler": self._get_satellite_data,
            },
        }

    def _register_resources(self):
        self._resources = {
            "agri://weather/current/{location}": {
                "name": "Météo Actuelle",
                "description": "Données météo en temps réel",
                "mime_type": "application/json",
                "handler": self._resource_current_weather,
            },
            "agri://weather/alerts/{zone}": {
                "name": "Alertes Climatiques",
                "description": "Alertes climatiques actives par zone",
                "mime_type": "application/json",
                "handler": self._resource_alerts,
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
            return {"error": f"Outil Weather inconnu: {name}", "status": "not_found"}
        try:
            result = tool["handler"](arguments)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "status": "ok",
            }
        except Exception as e:
            logger.error("MCP Weather call_tool error (%s): %s", name, e)
            return {"error": str(e), "status": "error"}

    def read_resource(self, uri: str, params: Dict = None) -> Dict[str, Any]:
        for pattern, resource in self._resources.items():
            if self._uri_matches(pattern, uri):
                try:
                    data = resource["handler"](params or self._extract_params(uri))
                    return {
                        "contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False)}],
                        "status": "ok",
                    }
                except Exception as e:
                    return {"error": str(e), "status": "error"}
        return {"error": f"Ressource Weather inconnue: {uri}", "status": "not_found"}

    # ═══════════════════════════════════════════════════════════
    # HANDLERS
    # ═══════════════════════════════════════════════════════════

    def _get_weather(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._lazy_tool()
        if not tool:
            return {"error": "Service météo indisponible"}
        location = arguments["location"]
        try:
            if hasattr(tool, "get_current_conditions"):
                return tool.get_current_conditions(location)
            elif hasattr(tool, "_get_weather_data"):
                return tool._get_weather_data(location)
            else:
                return {"location": location, "error": "Méthode météo non trouvée"}
        except Exception as e:
            return {"location": location, "error": str(e)}

    def _get_forecast(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._lazy_tool()
        if not tool:
            return {"error": "Service météo indisponible"}
        location = arguments["location"]
        days = arguments.get("days", 3)
        try:
            if hasattr(tool, "get_forecast"):
                return tool.get_forecast(location, days=days)
            else:
                return {"location": location, "days": days, "forecast": [], "note": "Prévisions non disponibles"}
        except Exception as e:
            return {"location": location, "error": str(e)}

    def _get_alerts(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._lazy_tool()
        if not tool:
            return {"error": "Service météo indisponible"}
        zone = arguments["zone"]
        try:
            if hasattr(tool, "get_alerts"):
                return tool.get_alerts(zone)
            elif hasattr(tool, "_analyze_hazards"):
                return {"zone": zone, "alerts": tool._analyze_hazards(zone)}
            else:
                return {"zone": zone, "alerts": [], "note": "Alertes non disponibles"}
        except Exception as e:
            return {"zone": zone, "error": str(e)}

    def _get_flood_risk(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._lazy_tool()
        if not tool:
            return {"error": "Service météo indisponible"}
        location = arguments["location"]
        try:
            if hasattr(tool, "flood_risk_assessment"):
                return tool.flood_risk_assessment(location)
            elif hasattr(tool, "_assess_flood_risk"):
                return tool._assess_flood_risk(location)
            else:
                return {"location": location, "risk": "unknown"}
        except Exception as e:
            return {"location": location, "error": str(e)}

    def _get_satellite_data(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._lazy_tool()
        if not tool:
            return {"error": "Service satellites indisponible"}
        location = arguments["location"]
        try:
            if hasattr(tool, "get_satellite_data"):
                return tool.get_satellite_data(location)
            elif hasattr(tool, "_get_satellite_signals"):
                return tool._get_satellite_signals(location)
            else:
                return {"location": location, "satellite": {}, "note": "Données satellites non disponibles"}
        except Exception as e:
            return {"location": location, "error": str(e)}

    def _resource_current_weather(self, params: Dict) -> Dict[str, Any]:
        return self._get_weather({"location": params.get("location", "ouagadougou")})

    def _resource_alerts(self, params: Dict) -> Dict[str, Any]:
        return self._get_alerts({"zone": params.get("zone", "centre")})

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _uri_matches(self, pattern: str, uri: str) -> bool:
        import re
        regex = pattern.replace("{location}", r"[^/]+").replace("{zone}", r"[^/]+")
        return bool(re.match(regex, uri))

    def _extract_params(self, uri: str) -> Dict[str, str]:
        parts = uri.replace("agri://weather/", "").split("/")
        if len(parts) >= 2:
            if parts[0] == "current":
                return {"location": parts[1]}
            elif parts[0] == "alerts":
                return {"zone": parts[1]}
        return {}
