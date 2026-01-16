import logging
import json
from datetime import datetime
from typing import TypedDict, Dict, Any, Optional, List

# --- Importations LangGraph & LangChain ---
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from tools.meteo.basis_tools import SahelAgriAdvisor, SoilType
from tools.meteo.flood_risk import FloodRiskTool

# Configuration du Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SahelAgent.Robust")

# ==============================================================================
# 1. ÉTAT DE L'AGENT
# ==============================================================================
class AgentState(TypedDict):
    user_query: str
    weather_data: Dict[str, Any]
    culture_info: Dict[str, Any]
    raw_diagnosis: Optional[Dict[str, Any]]
    flood_risk: Optional[Dict[str, Any]]
    final_response: str
    error_log: List[str]

# ==============================================================================
# 2. L'AGENT VIGILANCE CLIMATIQUE
# ==============================================================================
class ClimateVigilance:
    def __init__(self, model_name="llama3:8b", ollama_host="http://localhost:11434", llm_client=None):
        self.advisor = SahelAgriAdvisor()
        self.flood_tool = FloodRiskTool()
        self.llm_name = model_name
        
        try:
            self.llm = llm_client if llm_client else ChatOllama(
                model=self.llm_name, 
                base_url=ollama_host, 
                temperature=0.2 # Légère créativité pour les conseils
            )
        except Exception as e:
            logger.error(f"❌ Échec initialisation Ollama: {e}")
            self.llm = None

    # --- ÉTAPE 1: LOGIQUE MÉTIER (Calculs froids) ---
    def validate_and_calculate(self, state: AgentState) -> Dict[str, Any]:
        """Nettoie les données et exécute les outils agronomiques."""
        logger.info("--- NODE: VALIDATION & CALCULS ---")
        errors = []
        w = state.get("weather_data", {})
        c = state.get("culture_info", {})

        # 1. Validation de présence
        required_weather = ["t_min", "t_max", "rh", "precip"]
        for param in required_weather:
            if w.get(param) is None:
                errors.append(f"Donnée météo manquante : {param}")

        if not c.get("crop_name"):
            errors.append("Nom de la culture manquant")

        if errors:
            return {"error_log": errors}

        try:
            # 2. Conversion sécurisée et Calcul Agronomique
            diagnosis = self.advisor.get_daily_diagnosis(
                crop_key=c["crop_name"],
                soil=c.get("soil_type", SoilType.STANDARD),
                t_min=float(w["t_min"]),
                t_max=float(w["t_max"]),
                rh=float(w["rh"]),
                precip=float(w["precip"]),
                doy=datetime.now().timetuple().tm_yday,
                lat=float(c.get("lat", 12.37)),
                distance_km=25.0,
                # Nouveaux paramètres Météo Décisionnelle
                wind_speed_kmh=float(w.get("wind_speed", 10.0)),
                rain_prob_next_6h=float(w.get("rain_prob", 0.0))
            )
            
            # 3. Risque Inondation
            location = c.get("location", "ouagadougou")
            lat = float(c.get("lat", 12.37))
            lon = float(c.get("lon", -1.52))
            flood_risk = self.flood_tool.check_flood_risk(location, lat, lon)
            
            return {
                "raw_diagnosis": diagnosis, 
                "flood_risk": flood_risk, 
                "error_log": []
            }

        except Exception as e:
            logger.error(f"💥 Erreur calcul : {e}")
            return {"error_log": [f"Erreur technique : {str(e)}"]}

    # --- ÉTAPE 2: SYNTHÈSE EXPERTE (Langage chaud) ---
    def generate_expert_response(self, state: AgentState) -> Dict[str, Any]:
        """Génère le conseil final avec un ton adapté au Sahel."""
        if state.get("error_log"):
            return {"final_response": f"⚠️ Impossible de formuler un conseil : {', '.join(state['error_log'])}."}

        diag = state["raw_diagnosis"]
        flood = state["flood_risk"]
        
        # [MODIF] Injection des Alertes Critiques Calculées Techniquement
        # Cela force l'IA à respecter les interdits (Pilier 3)
        critical_alerts = diag.get("alerts_critiques", [])

        if not self.llm:
            return {"final_response": self._fallback_template(diag, flood)}

        # Prompt optimisé pour le terrain
        system_prompt = (
            "Tu es 'Sentinelle d'AgriConnect', l'expert agricole du Sahel.\n"
            "TON : Respectueux, direct, encourageant. Utilise des images simples.\n"
            "RÈGLES CRITIQUES :\n"
            "1. INTERDICTIONS : Si la liste 'CRITICAL_ALERTS' contient des éléments, TU DOIS COMMENCER par eux écrit en MAJUSCULES.\n"
            "2. EXPLICABILITÉ : Explique toujours 'Pourquoi' (ex: 'Ne sème pas car le sol est sec').\n"
            "3. FORMAT : Court et lisible."
        )
        
        human_content = (
            f"Question Agriculteur : '{state['user_query']}'\n\n"
            f"--- DONNÉES TECHNIQUES ---\n"
            f"Culture : {diag.get('culture')}\n"
            f"RISQUE INONDATION : {flood.get('risk_level')} ({flood.get('alert_message')})\n"
            f"CRITICAL_ALERTS (A RESPECTER ABSOLUMENT) : {json.dumps(critical_alerts, ensure_ascii=False)}\n"
            f"Bilan Hydrique : {diag.get('bilan')} mm\n"
            f"Recommandations Techniques : {diag.get('recommandations')}"
        )

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_content)
            ])
            return {"final_response": response.content}
        except Exception:
            return {"final_response": self._fallback_template(diag, flood)}

    def _fallback_template(self, diag: Dict, flood: Dict) -> str:
        """Rendu textuel si l'IA est hors-ligne."""
        res = "📢 [CONSEIL AUTOMATIQUE]\n"
        if flood.get("risk_level") in ["Élevé", "Critique"]:
            res += f"🚨 ALERTE INONDATION : {flood['alert_message']}\n"
        
        res += f"✅ Culture : {diag.get('culture', 'Inconnue')}\n"
        res += f"💧 Besoin en eau : {diag.get('besoin_eau_etc_mm')} mm\n"
        res += f"🚜 Conseil : {diag.get('conseil_irrigation', "Vérifiez l'humidité du sol")}"
        return res

    def build(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("logic", self.validate_and_calculate)
        workflow.add_node("expert", self.generate_expert_response)
        workflow.set_entry_point("logic")
        workflow.add_edge("logic", "expert")
        workflow.add_edge("expert", END)
        return workflow.compile()