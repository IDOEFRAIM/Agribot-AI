import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from orchestrator.state import GlobalAgriState
from services.utils.cache import StorageManager
from agents.climate_vigilance import ClimateVigilance
from agents.agri_business_coach import AgriBusinessCoach
from tools.collaboration.alert_reporter import AlertReporter

logger = logging.getLogger("MessageFlow")

class MessageResponseFlow:
    """
    Orchestrateur LangGraph pour fusionner l'intelligence climatique, 
    économique (Agri-Business), et collaborative (Sentinelle).
    """
    def __init__(self, llm_client=None):
        self.storage = StorageManager() 
        
        # Configuration du LLM de synthèse (Llama 3)
        try:
            self.llm = llm_client if llm_client else ChatOllama(model="llama3:8b", keep_alive=-1)
        except Exception as e:
            logger.warning(f"Orchestrator LLM init failed: {e}")
            self.llm = None

        # Agents spécialisés
        self.meteo_agent = ClimateVigilance(llm_client=llm_client)
        self.market_agent = AgriBusinessCoach(llm_client=llm_client)
        
        # Nouveaux modules Piliers 1 & 4
        self.alert_tool = AlertReporter()

    def run_reporting(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Gère les signalements (Pilier 1 : La Sentinelle)."""
        logger.info("--- NODE: REPORTING ---")
        query = state.get("requete_utilisateur", "") or "Signalement vide"
        user_id = state.get("user_id", "anonymous")
        zone_id = state.get("zone_id", "unknown")
        
        report_result = self.alert_tool.report_event(
            user_id=user_id,
            zone_id=zone_id,
            description=query,
            event_type="USER_REPORT"
        )
        
        # Mise à jour du Trust Score (Pilier 2)
        current_score = state.get("user_reliability_score", 0.5)
        bonus = report_result.get("trust_score_update", 0)
        # On plafonne à 1.0, chaque action positive donne un petit boost
        new_score = min(1.0, current_score + (bonus / 100.0))
        
        return {
            "final_response": report_result["response"],
            "user_reliability_score": new_score
        }

    def run_meteo(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Exécute l'analyse climatique et hydrique."""
        logger.info("--- NODE: CLIMATE VIGILANCE ---")
        zone_id = state.get("zone_id", "Centre")
        
        # Simulation/Récupération des données locales (Devraient être fetchées d'une API externe)
        weather_data = {
            "t_min": 25, 
            "t_max": 35, 
            "rh": 40, 
            "precip": 0, 
            "wind_speed": 12,    # Ajout Pilier 3 (Sécurité)
            "rain_prob": 10      # Ajout Pilier 3 (Sécurité)
        } 
        
        try:
            # En production, on utiliserait self.storage pour récupérer la météo réelle via API
            raw = self.storage.get_raw_data(zone_id=zone_id, category="METEO_VECTOR", limit=1)
            if raw: weather_data.update(raw[0])
        except Exception as e:
            logger.error(f"Erreur cache météo: {e}")

        # Construction explicite pour satisfaire le typage strict
        agent_state = {
            "user_query": str(state.get("requete_utilisateur", "")),
            "weather_data": weather_data,
            "culture_info": {"crop_name": str(state.get("crop", "Maïs")), "location": str(zone_id)},
            "final_response": "",
            "raw_diagnosis": None,
            "flood_risk": None,
            "error_log": []
        }
        
        # Cycle interne de l'agent météo
        res = self.meteo_agent.validate_and_calculate(agent_state)
        # Gestion d'erreur robuste : Si l'agent échoue, on ne bloque pas tout le flux
        if res.get("error_log"):
            logger.error(f"Erreur agent météo: {res['error_log']}")
            return {"meteo_info": "Données météo indisponibles."}
            
        agent_state.update(res)
        final = self.meteo_agent.generate_expert_response(agent_state)
        
        return {"meteo_info": final["final_response"]}

    def market_node(self, state: GlobalAgriState):
        logger.info("--- NODE: MARKET AGENT ---")
        # Construction typée pour Agent Marché
        agent_state = {
            "zone_id": str(state.get("zone_id", "Centre")),
            "user_query": str(state.get("requete_utilisateur", "")),
            "user_profile": {"crop": str(state.get("crop", "Maïs"))},
            "final_response": "",
            "technical_advice_raw": None,
            "status": "INIT",
            "metadata": {}
        }
        
        # Cycle interne de l'agent marché
        res = self.market_agent.analyze_node(agent_state)
        agent_state.update(res)
        final = self.market_agent.format_node(agent_state)
        
        return {"market_info": final["final_response"]}

    def synthesize_answer(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Nœud de décision final : Fusionne les risques climatiques et les gains économiques.
        """
        query = state.get("requete_utilisateur", "")
        meteo_resp = state.get("meteo_info", "Alerte : Données météo manquantes.")
        market_resp = state.get("market_info", "Alerte : Données marché manquantes.")

        if not self.llm:
            return {"final_response": f"{meteo_resp}\n\n---\n\n{market_resp}"}
            
        system_prompt = (
            "Tu es le Superviseur AgriConnect Expert. Ton rôle est de fournir un conseil "
            "stratégique cross-domaine (Climat + Marché) pour un agriculteur au Burkina Faso.\n\n"
            "DIRECTIVES :\n"
            "1. L'action doit être PRIORITAIRE (ex: Ne pas épandre d'engrais s'il va pleuvoir, même si le prix est bon).\n"
            "2. Calcule l'impact financier du risque climatique si possible.\n"
            "3. Utilise un ton de 'grand frère' expert, pragmatique et rassurant.\n"
            "4. Structure la réponse : 1. Action Immédiate | 2. Analyse Risque/Gain | 3. Conseil Marché."
        )
        
        try:
            human_msg = (
                f"REQUÊTE : '{query}'\n\n"
                f"CONTEXTE CLIMATIQUE : {meteo_resp}\n\n"
                f"CONTEXTE ÉCONOMIQUE : {market_resp}\n\n"
                "CONSEIL STRATÉGIQUE :"
            )
            res = self.llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=human_msg)])
            return {"final_response": res.content}
        except Exception as e:
            logger.error(f"Echec synthèse: {e}")
            return {"final_response": f"Stratégie Climat: {meteo_resp}\nStratégie Marché: {market_resp}"}

    def build_graph(self):
        """Compile le workflow de décision dynamique."""
        workflow = StateGraph(GlobalAgriState)
        
        # Définition des nœuds
        # On garde les nœuds principaux pour le test
        workflow.add_node("meteo_node", self.run_meteo)
        workflow.add_node("market_node", self.market_node)
        workflow.add_node("synthesizer_node", self.synthesize_answer)
        
        # MODE TEST : On force le passage par Météo puis Marché
        # On contourne le classifieur et le reporting pour l'instant
        workflow.set_entry_point("meteo_node")
        
        # Flux Expert (Meteo -> Market -> Synthèse)
        workflow.add_edge("meteo_node", "market_node")
        workflow.add_edge("market_node", "synthesizer_node")
        workflow.add_edge("synthesizer_node", END)
        
        return workflow.compile()