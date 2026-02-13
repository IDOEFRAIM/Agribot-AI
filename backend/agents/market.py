import json
import logging
import re
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from backend.agents.system.prompts import (
    MARKET_EXTRACT_INTENT_TEMPLATE,
    MARKET_MODERATE_FINANCE_TEMPLATE,
    MARKET_SYSTEM_PROMPT_TEMPLATE,
    MARKET_USER_PROMPT_TEMPLATE,
)
from ..rag.components import get_groq_sdk
from ..tools.market import AgrimarketTool

logger = logging.getLogger("Agent.MarketCoach")

class MarketAgentState(TypedDict, total=False):
    user_query: str
    user_profile: Dict[str, Any]
    user_level: str
    intent: str  # CHECK_PRICE, SELL_OFFER, BUY_OFFER, SCAM_CHECK, REGISTER_SURPLUS
    product: str
    location: str
    price_mentioned: Optional[float]
    quantity_mentioned: Optional[float]
    market_data: Dict[str, Any]
    scam_analysis: Dict[str, Any]
    final_response: str
    status: str
    warnings: List[str]
    security_status: str
    security_reason: str

class MarketCoach:
    def __init__(self, llm_client=None):
        self.model_planner = "llama-3.1-8b-instant"
        self.model_answer = "llama-3.3-70b-versatile"
        self.tool = AgrimarketTool()

        try:
            self.llm = llm_client if llm_client else get_groq_sdk()
        except Exception as exc:
            logger.error("Impossible d'initialiser le LLM : %s", exc)
            self.llm = None

    # ------------------------------------------------------------------ #
    # Nœuds du graphe                                                    #
    # ------------------------------------------------------------------ #

    def analyze_node(self, state: MarketAgentState) -> MarketAgentState:
        """
        Analyse l'intention financière : Demande de prix, Offre, ou Arnaque potentielle.
        C'est ici que se joue la sécurité financière.
        """
        state = dict(state)
        query = state.get("user_query", "").strip()
        warnings = list(state.get("warnings", []))

        if not query:
            return {"status": "ERROR", "warnings": ["Question vide"]}

        # 1. D'abord, on vérifie si c'est une arnaque (Le Market Agent est le gardien financier)
        moderation = self._moderate_finance(query)
        if moderation.get("is_scam"):
            state.update({
                "security_status": "SCAM_DETECTED",
                "security_reason": moderation.get("reason"),
                "status": "SCAM_DETECTED"
            })
            return state

        # 2. Si c'est sûr, on analyse le besoin commercial
        analysis = self._extract_market_intent(query)
        
        state.update({
            "intent": analysis.get("intent", "CHECK_PRICE"),
            "product": analysis.get("product"),
            "location": analysis.get("location"),
            "price_mentioned": analysis.get("price"),
            "quantity_mentioned": analysis.get("quantity"),
            "security_status": "SAFE",
            "status": "ANALYZED"
        })
        return state

    def fetch_data_node(self, state: MarketAgentState) -> MarketAgentState:
        """
        Récupère les données de marché via AgrimarketTool.
        """
        state = dict(state)
        if state.get("status") == "SCAM_DETECTED":
            return state

        product = state.get("product")
        intent = state.get("intent")
        location = state.get("location")
        quantity = state.get("quantity_mentioned", 0)
        
        data = {}

        # Si l'utilisateur veut ENREGISTRER UN SURPLUS
        if (intent == "REGISTER_SURPLUS" or intent == "SELL") and product and quantity:
            # 1. Enregistrement
            success = self.tool.register_surplus_offer(product, quantity, location or "Inconnu")
            data["registration_status"] = "SUCCESS" if success else "OFFLINE_SAVED"
            
            # 2. Récupération des infos logistiques locales
            if location:
                data["logistics"] = self.tool.get_logistics_info(location)
            
            # On continue pour récupérer aussi les tendances et donner un conseil
        
        # Récupération des prix
        if product:
            prices = self.tool.get_commodity_price(product)
            if prices:
                data["prices"] = prices
            
            # Analyse de volatilité/tendance
            data["trends"] = self.tool.analyze_market_trends(product)
        
        # Récupération des offres pour l'intention inverse (si je veux vendre, je cherche des acheteurs)
        # Note: ceci est une simplification, l'outil réel pourrait avoir besoin de plus de paramètres
        # Pour l'instant on simule ou on utilise ce qui est dispo
        
        state.update({
            "market_data": data,
            "status": "DATA_FETCHED"
        })
        return state

    def compose_node(self, state: MarketAgentState) -> MarketAgentState:
        state = dict(state)
        status = state.get("status")
        
        if status == "SCAM_DETECTED":
            response = self._build_scam_alert(state)
            state.update({"final_response": response})
            return state

        # Construction de la réponse commerciale
        response = self._generate_market_response(state)
        state.update({"final_response": response, "status": "COMPLETED"})
        return state

    # ------------------------------------------------------------------ #
    # Utilitaires & Prompts                                              #
    # ------------------------------------------------------------------ #

    def _extract_json_block(self, text: str) -> Dict[str, Any]:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    def _moderate_finance(self, query: str) -> Dict[str, Any]:
        """Détecte les arnaques financières, demandes d'argent, etc."""
        if not self.llm:
            return {"is_scam": False}

        
        
        try:
            # 1. On remplit le template avec la requête utilisateur
            formatted_finance_prompt = MARKET_MODERATE_FINANCE_TEMPLATE.format(query=query)

            # 2. On l'envoie au LLM
            resp = self.llm.chat.completions.create(
                model=self.model_planner,
                messages=[{"role": "user", "content": formatted_finance_prompt}],
                temperature=0,
                response_format={"type": "json_object"} 
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.warning("Erreur moderation market: %s", e)
            return {"is_scam": False}

    def _build_scam_alert(self, state: MarketAgentState) -> str:
        reason = state.get("security_reason", "Activité suspecte.")
        return (
            "🚨 **ALERTE SÉCURITÉ FINANCIÈRE**\n\n"
            f"{reason}\n\n"
            "⛔ **RÈGLE D'OR :** AgriConnect ne vous demandera **JAMAIS** de transfert d'argent "
            "par téléphone pour débloquer une aide ou un prix.\n"
            "Si on vous promet un prix 50% au-dessus du marché, c'est probablement une arnaque."
        )

    def _extract_market_intent(self, query: str) -> Dict[str, Any]:
        
        try:
            # 1. Injection de la requête dans le template d'extraction
            # Assure-toi que MARKET_EXTRACT_INTENT_TEMPLATE est le nom dans ton prompts.py
            formatted_intent_prompt = MARKET_EXTRACT_INTENT_TEMPLATE.format(query=query)

            # 2. Appel au LLM (Modèle Planner / Léger)
            resp = self.llm.chat.completions.create(
                model=self.model_planner,
                messages=[{"role": "user", "content": formatted_intent_prompt}],
                temperature=0, # On reste à 0 pour une extraction stricte et constante
                response_format={"type": "json_object"}
            )

            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.warning("Erreur extraction intent: %s", e)
            return {"intent": "CHECK_PRICE"}

    def _generate_market_response(self, state: MarketAgentState) -> str:
        data = state.get("market_data", {})
        intent = state.get("intent")
        product = state.get("product")
        status = state.get("status")
        location = state.get("location", "votre région")
        
        intro_msg = ""
        # Si on a enregistré un surplus
        reg_status = data.get("registration_status")
        logistics = data.get("logistics", {})
        
        if reg_status == "SUCCESS":
            intro_msg = (
                f"✅ **Offre validée !**\n"
                f"Vos {state.get('quantity_mentioned')} de {product} sont enregistrés dans la base nationale SONAGESS.\n"
            )
        elif reg_status == "OFFLINE_SAVED":
            intro_msg = (
                f"📂 **Offre sauvegardée (Mode Connexion Faible)**\n"
                f"J'ai noté vos {state.get('quantity_mentioned')} de {product} dans votre dossier temporaire.\n"
                "La synchronisation avec la SONAGESS se fera automatiquement dès le retour du réseau.\n"
            )
        
        # Ajout systématique de l'appel à l'action logistique si vente
        if reg_status and logistics:
            intro_msg += (
                f"\n📍 **Action requise :**\n"
                f"Le point de collecte SONAGESS le plus proche est à : **{logistics.get('sonagess_center')}**.\n"
                "Voulez-vous que je leur envoie vos coordonnées GPS pour le ramassage ?\n\n"
                "⚖️ **Précision importante :** S'agit-il de sacs de **50kg** ou de **100kg** ? C'est important pour les camions.\n\n"
            )

        if not product and intent == "CHECK_PRICE":
            return intro_msg + "De quel produit souhaitez-vous connaître le prix ? (Maïs, Sorgho, Mil, Riz...)"
            
        
        
        try:
            # 1. Préparation du prompt Système (avec les données data et logistics)
            # On convertit les dictionnaires en JSON string pour l'affichage dans le prompt
            system_content = MARKET_SYSTEM_PROMPT_TEMPLATE.format(
                market_data=json.dumps(data, ensure_ascii=False),
                logistics_data=json.dumps(logistics, ensure_ascii=False)
            )

            # 2. Préparation du prompt Utilisateur (avec la query de l'état)
            user_content = MARKET_USER_PROMPT_TEMPLATE.format(
                query=state.get('user_query')
            )

            # 3. Appel au LLM
            resp = self.llm.chat.completions.create(
                model=self.model_answer,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning("Erreur génération réponse marché: %s", e)
            return "Désolé, je ne peux pas accéder aux données du marché pour le moment."

    def build(self):
        workflow = StateGraph(MarketAgentState)
        workflow.add_node("analyze", self.analyze_node)
        workflow.add_node("fetch_data", self.fetch_data_node)
        workflow.add_node("compose", self.compose_node)

        workflow.set_entry_point("analyze")
        
        def route_analysis(state):
            if state.get("status") == "SCAM_DETECTED":
                return "compose"
            if state.get("status") == "ERROR":
                return END
            return "fetch_data"

        workflow.add_conditional_edges("analyze", route_analysis)
        workflow.add_edge("fetch_data", "compose")
        workflow.add_edge("compose", END)
        
        return workflow.compile()


if __name__ == "__main__":
    # 1. Initialisation du coach et compilation du graph
    coach = MarketCoach()
    app = coach.build()

    # Configuration des tests
    test_cases = [
        {
            "name": "DEMANDE DE PRIX",
            "query": "Quel est le prix actuel du sac de maïs de 100kg à Dédougou ?"
        },
        {
            "name": "DÉTECTION D'ARNAQUE",
            "query": "Félicitations ! Vous avez gagné une aide de 500.000 FCFA du ministère. Envoyez 10.000 FCFA par Orange Money au 07000000 pour débloquer votre dossier."
        },
        {
            "name": "ENREGISTREMENT SURPLUS",
            "query": "J'ai 50 sacs de maïs à vendre à Nouna."
        }
    ]

    print("🚀 Démarrage des tests AgriConnect Market Coach...\n")

    for case in test_cases:
        print(f"--- TEST : {case['name']} ---")
        print(f"Question : {case['query']}")
        
        # Initialisation de l'état
        initial_state = {
            "user_query": case['query'],
            "user_profile": {"niveau": "débutant", "région": "Boucle du Mouhoun"},
            "warnings": []
        }

        # Exécution du graph
        try:
            result = app.invoke(initial_state)
            
            print(f"Statut Final : {result.get('status')}")
            print(f"Intention détectée : {result.get('intent')}")
            print(f"Réponse de l'Agent :\n{result.get('final_response')}")
            
        except Exception as e:
            print(f"❌ Erreur lors de l'exécution : {e}")
        
        print("-" * 50 + "\n")