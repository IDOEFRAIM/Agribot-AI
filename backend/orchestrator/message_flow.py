import logging
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from groq_client import client
from langchain_core.messages import SystemMessage

# Imports internes (supposés existants selon votre contexte)
from orchestrator.state import GlobalAgriState
from orchestrator.intention import IntentClassifier  # Votre nouvelle classe optimisée
from agents.climate_vigilance import ClimateVigilance
from agents.agri_business_coach import AgriBusinessCoach

logger = logging.getLogger("MessageFlow")

class MessageResponseFlow:

    def __init__(self, llm_client=None):
        self.llm = llm_client if llm_client is not None else client
        
        # 1. Initialisation des Agents
        self.meteo_agent = ClimateVigilance(llm_client=self.llm)
        self.market_agent = AgriBusinessCoach(llm_client=self.llm)
        
        # 2. Initialisation du Classificateur
        self.intent_classifier = IntentClassifier(llm_client=self.llm)

    # ============================================================
    # NODES (Les étapes du Graphe)
    # ============================================================

    def detect_intent_step(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Nœud 1 : Analyse l'intention de l'utilisateur.
        """
        logger.info("--- NODE: INTENT DETECTION ---")
        query = state.get("requete_utilisateur", "")
        
        # Appel au classificateur optimisé
        intent = self.intent_classifier.predict(query)
        logger.info(f"🔎 Intention détectée : {intent}")
        
        return {"intent": intent}

    def run_meteo(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Nœud Météo : Exécute l'agent climatique.
        """
        logger.info("--- NODE: CLIMATE VIGILANCE ---")
        zone_id = state.get("zone_id", "boromo")
        
        # Récupération DB (Simulation ou appel réel)
        try:
            from tools.weather_db_utils import get_unique_weather_data
            from datetime import datetime
            
            mois = datetime.now().month
            row = get_unique_weather_data(city=zone_id.capitalize(), month=mois)
            
            weather_data = {
                "t_min": row.get("t_min") if row else 20,
                "t_max": row.get("t_max") if row else 35,
                "rh": row.get("rh") if row else 40,
                "precip": row.get("precip") if row else 0
            }
        except Exception as e:
            logger.warning(f"DB Error: {e}, using defaults.")
            weather_data = {"t_min": 22, "t_max": 38, "rh": 30, "precip": 0}

        # Construction de l'état local de l'agent
        agent_state = {
            "user_query": state.get("requete_utilisateur"),
            "weather_data": weather_data,
            "culture_info": {"crop_name": state.get("crop", "Maïs"), "location": zone_id},
            "final_response": "",
            "error_log": []
        }

        # Exécution de l'agent Météo
        res = self.meteo_agent.validate_and_calculate(agent_state)
        agent_state.update(res)
        final = self.meteo_agent.generate_expert_response(agent_state)
        
        return {"meteo_info": final["final_response"]}

    def run_market(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Nœud Marché : Exécute l'agent économique.
        """
        logger.info("--- NODE: MARKET AGENT ---")
        
        agent_state = {
            "zone_id": state.get("zone_id", "boromo"),
            "user_query": state.get("requete_utilisateur"),
            "user_profile": {"crop": state.get("crop", "Maïs")},
            "final_response": "",
            "status": "INIT"
        }
        
        # Exécution de l'agent Marché
        res = self.market_agent.analyze_node(agent_state)
        agent_state.update(res)
        final = self.market_agent.format_node(agent_state)
        
        return {"market_info": final["final_response"]}

    def synthesize_mixte(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Nœud Synthèse : Uniquement activé si Intent == MIXTE.
        Fusionne les infos météo et marché.
        """
        logger.info("--- NODE: SYNTHESIS (MIXTE) ---")
        meteo = state.get("meteo_info", "Pas d'info météo")
        market = state.get("market_info", "Pas d'info marché")
        
        prompt = (
            "Tu es un conseiller agricole expert. L'utilisateur a posé une question complexe.\n"
            f"INFO MÉTÉO : {meteo}\n"
            f"INFO MARCHÉ : {market}\n\n"
            "Synthétise ces deux informations en une réponse cohérente, courte et utile."
        )
        
        try:
            res = self.llm.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}]
            )
            return {"final_response": res.choices[0].message.content}
        except:
            return {"final_response": f"Météo : {meteo}\n\nMarché : {market}"}

    def handle_unknown(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Nœud Fallback : Si l'intention n'est pas claire.
        """
        return {"final_response": "Je suis spécialisé en Météo agricole et Prix du marché. Pouvez-vous reformuler votre question sur ces sujets ?"}

    def format_output(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Nœud Final : Assure que la réponse est bien placée dans 'final_response'
        si on vient d'un chemin simple (Meteo seule ou Marché seul).
        """
        intent = state.get("intent")
        
        # Si c'était une voie simple, on déplace l'info spécifique vers la réponse finale
        if intent == "METEO" and not state.get("final_response"):
            return {"final_response": state.get("meteo_info")}
        
        if intent == "MARCHE" and not state.get("final_response"):
            return {"final_response": state.get("market_info")}
            
        return {} # Si MIXTE ou UNKNOWN, final_response est déjà rempli

    # ============================================================
    # CONSTRUCTION DU GRAPH (ROUTING)
    # ============================================================

    def route_intent(self, state: GlobalAgriState) -> Literal["meteo", "market", "mixte", "unknown"]:
        """
        Logique de décision pour les arêtes conditionnelles.
        """
        intent = state.get("intent", "UNKNOWN")
        
        if intent == "METEO":
            return "meteo"
        elif intent == "MARCHE": # Note : Assurez-vous que l'IntentClassifier renvoie "MARCHE"
            return "market"
        elif intent == "MIXTE":
            return "mixte"
        else:
            return "unknown"

    def build_graph(self):
        workflow = StateGraph(GlobalAgriState)

        # 1. Ajout des Nœuds
        workflow.add_node("detect_intent", self.detect_intent_step)
        workflow.add_node("meteo_node", self.run_meteo)
        workflow.add_node("market_node", self.run_market)
        workflow.add_node("synthesis_node", self.synthesize_mixte)
        workflow.add_node("unknown_node", self.handle_unknown)
        workflow.add_node("format_node", self.format_output)

        # 2. Définition du Point d'Entrée
        workflow.set_entry_point("detect_intent")

        # 3. Arêtes Conditionnelles (Le Cœur du Routeur)
        workflow.add_conditional_edges(
            "detect_intent",
            self.route_intent,
            {
                "meteo": "meteo_node",
                "market": "market_node",
                "mixte": "meteo_node", # Mixte commence par météo...
                "unknown": "unknown_node"
            }
        )

        # 4. Chemins Simples
        workflow.add_edge("meteo_node", "format_node") # Si Meteo seule -> Format -> Fin
        workflow.add_edge("market_node", "format_node") # Si Marché seul -> Format -> Fin
        workflow.add_edge("unknown_node", END)

        # 5. Chemin Mixte (Le pont spécifique)
        # Il faut une condition après meteo_node pour savoir si on continue vers market (cas mixte) ou si on s'arrête (cas meteo simple)
        # MAIS pour simplifier ici : 
        # J'utilise une astuce : Dans le cas MIXTE, on chaine manuellement via conditional edge
        
        # Redéfinition des sorties de meteo_node pour gérer le cas MIXTE
        # On écrase l'edge simple défini ci-dessus pour meteo_node par un conditional
        def route_after_meteo(state):
            if state.get("intent") == "MIXTE":
                return "go_market"
            return "go_end"

        workflow.add_conditional_edges(
            "meteo_node",
            route_after_meteo,
            {
                "go_market": "market_node", # Mixte : on enchaîne
                "go_end": "format_node"     # Solo : on finit
            }
        )
        
        # Pareil pour market_node : si MIXTE, on va à la synthèse
        def route_after_market(state):
            if state.get("intent") == "MIXTE":
                return "go_synthesis"
            return "go_end"

        workflow.add_conditional_edges(
            "market_node",
            route_after_market,
            {
                "go_synthesis": "synthesis_node",
                "go_end": "format_node"
            }
        )

        workflow.add_edge("synthesis_node", END)
        workflow.add_edge("format_node", END)

        return workflow.compile()

    def run(self, initial_state: GlobalAgriState):
        app = self.build_graph()
        return app.invoke(initial_state)