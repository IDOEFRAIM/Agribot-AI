"""
Main Orchestrator - Point d'entrée central d'Agribot
=====================================================

PHILOSOPHIE : "Simplicité avant Complexité"
--------------------------------------------
Au lieu de router dès le départ, on commence par :
1. Comprendre QUI parle (agriculteur, extension agent, chercheur)
2. Détecter les URGENCES (criquets, sécheresse extrême, maladie fulgurante)
3. Choisir le BON MODE de réponse (SMS court, vocal, texte long)
4. Router intelligemment vers message_flow OU report_flow

OBJECTIF : Agriculteur appelle → Réponse UTILE en < 10 secondes
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from langgraph.graph import StateGraph, END

from .state import GlobalAgriState, Severity, Alert
from .message_flow import MessageResponseFlow
from .report_flow import ReportFlow
from .central_data_manager import CentralDataManager
from .intention import AgriScopeChecker
from backend.rag.components import get_llm_client
from backend.utils.typo_corrector import AgriTypoCorrector

logger = logging.getLogger("MainOrchestrator")

# ── Config : réponses d'urgence (pas de texte hardcodé dans le code) ─────
EMERGENCY_RESPONSES = {
    "criquet": (
        "🚨 URGENCE CRIQUETS:\n"
        "1. IMMÉDIAT: Pulvériser eau savonneuse (300g savon/10L)\n"
        "2. Appeler: Service Phyto [NUMERO]\n"
        "3. Prévenir voisins - invasion rapide!\n"
        "4. Photos → envoyer au 55555\n\n"
        "Un expert vous rappelle en < 30min."
    ),
    "sécheresse": (
        "🚨 URGENCE EAU:\n"
        "1. STOP irrigation plein soleil\n"
        "2. Paillage urgent (paille/feuilles)\n"
        "3. Arroser tôt matin ou soir\n"
        "4. Prioriser jeunes plants\n\n"
        "Météo 7j → demandez 'prévisions'"
    ),
    "default": (
        "🚨 URGENCE DÉTECTÉE\n"
        "Un conseiller vous contacte sous 30 minutes.\n"
        "En attendant:\n"
        "- Photos du problème\n"
        "- Isoler plants malades\n"
        "- NE PAS TRAITER sans diagnostic\n\n"
        "Hotline: [NUMERO URGENCE]"
    ),
    "sms": "🚨URGENT! Conseiller rappelle<30min. Isolez plants malades. Photos→55555",
}


class AgribotMainOrchestrator:
    """
    Coordinateur Central Agribot - Le Conseiller Principal.
    
    Décide si :
    - C'est une URGENCE → Réponse immédiate + escalade
    - C'est une QUESTION → message_flow (multi-experts)
    - C'est un RAPPORT AUTO → report_flow (à implémenter)
    
    NOUVEAUX GARDE-FOUS:
    - ✏️ Correction automatique fautes (inera→INERA)
    - 🧠 Détection hors-sujet par LLM (scalable, pas keyword-based)
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client if llm_client else get_llm_client()
        self.data_manager = CentralDataManager()
        self.message_flow = MessageResponseFlow(llm_client=self.llm)
        self.report_flow = ReportFlow(llm_client=self.llm)
        
        # NOUVEAUX: Garde-fous qualité
        self.typo_corrector = AgriTypoCorrector()
        self.agriscope_checker = AgriScopeChecker(llm_client=self.llm)
        
        self.graph = self._build_orchestrator_graph()

    # ------------------------------------------------------------------ #
    # NODES DU GRAPHE PRINCIPAL
    # ------------------------------------------------------------------ #

    def triage_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        TRIAGE INTELLIGENT avec GARDE-FOUS.
        
        Étapes:
        0. ✏️ Correction automatique fautes (inera→INERA)
        1. 🧠 Vérification agricole par LLM (rejeter Vietnam, rap...)
        2. 🚨 Détection urgences agricoles
        3. 📱 Adaptation mode communication
        4. 🎯 Type de flow (MESSAGE/REPORT/GREETING)
        """
        logger.info("🚦 TRIAGE: Analyse de la requête entrante...")
        
        query_original = state.get("requete_utilisateur", "").strip()
        zone_id = state.get("zone_id", "default")
        crop = state.get("crop", "inconnu")
        is_sms = state.get("is_sms_mode", False)
        
        # ÉTAPE 0: CORRECTION AUTOMATIQUE FAUTES
        query_corrected, corrections = self.typo_corrector.correct_query(query_original)
        if corrections:
            logger.info(f"✏️ Corrections appliquées: {corrections}")
        
        query = query_corrected.lower()
        
        # ÉTAPE 1: VÉRIFICATION SCOPE AGRICOLE (LLM)
        scope_result = self.agriscope_checker.check_scope(query_corrected)
        is_agricultural = scope_result["is_agricultural"]
        off_topic_reason = scope_result["reason"]
        
        if not is_agricultural:
            logger.warning(f"🚫 Question HORS-SUJET rejetée: {off_topic_reason}")
            rejection_msg = f"""Désolé, je suis un assistant agricole spécialisé au Burkina Faso.

Je peux vous aider avec :
✅ Cultures (maïs, coton, sésame, etc.)
✅ Météo et climat
✅ Prix et marchés
✅ Santé des plantes
✅ Sols et engrais
✅ Contacts INERA, SONAGESS

Votre question: "{off_topic_reason}"

Comment puis-je vous aider avec votre agriculture ?"""
            
            return {
                "flow_type": "OFF_TOPIC",
                "is_agricultural": False,
                "off_topic_reason": off_topic_reason,
                "final_response": rejection_msg,
                "execution_path": ["triage", "rejected_off_topic"],
                "status": "OFF_TOPIC"
            }
        
        # Question acceptée - on continue
        logger.info(f"✅ Question AGRICOLE acceptée (conf: {scope_result['confidence']:.2f})")
        # Question acceptée - on continue
        logger.info(f"✅ Question AGRICOLE acceptée (conf: {scope_result['confidence']:.2f})")
        
        # ÉTAPE 2: DÉTECTION D'URGENCE (Mots-clés critiques)
        urgency_keywords = {
            "CRITICAL": ["criquet", "invasion", "tous meurent", "catastrophe", "urgent help"],
            "HIGH": ["séchage", "flétrissement rapide", "perte massive", "tous malades"],
            "MEDIUM": ["inquiet", "problème", "aide", "que faire"]
        }
        
        detected_urgency = None
        for severity, keywords in urgency_keywords.items():
            if any(kw in query for kw in keywords):
                detected_urgency = severity
                break
        
        # ÉTAPE 3: DÉTECTION TYPE DE REQUÊTE
        if not query or query in ["bonjour", "salut", "hello"]:
            flow_type = "GREETING"
        elif "rapport" in query or "bilan" in query:
            flow_type = "REPORT"
        else:
            flow_type = "MESSAGE"
        
        # ÉTAPE 4: ADAPTATION AU MODE SMS (Réponses ultra-courtes)
        max_response_length = 160 if is_sms else 2000
        
        result = {
            "flow_type": flow_type,
            "is_agricultural": True,
            "off_topic_reason": None,
            "execution_path": ["triage"],
            "requete_utilisateur": query_corrected,  # Utiliser la version corrigée
        }
        
        # ÉTAPE 5: ALERTE URGENCE si détectée
        if detected_urgency:
            alert = Alert(
                source="triage",
                message=f"Urgence {detected_urgency} détectée: {query[:50]}",
                severity=Severity[detected_urgency]
            )
            result["global_alerts"] = [alert]
            logger.warning(f"🚨 URGENCE {detected_urgency}: {query[:50]}")
        
        return result

    def greeting_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Réponse rapide aux salutations - Pas besoin d'AI lourde.
        """
        logger.info("👋 GREETING: Salutation rapide")
        
        user_id = state.get("user_id", "agriculteur")
        crop = state.get("crop", "votre culture")
        
        greetings = [
            f"Bonjour {user_id}! Comment puis-je aider votre {crop} aujourd'hui?",
            f"Salut! Besoin d'un conseil pour votre {crop}?",
            f"Bonjour! Météo, marché, ou santé des plantes - que voulez-vous savoir?"
        ]
        
        import random
        response = random.choice(greetings)
        
        if state.get("is_sms_mode"):
            response = f"Bonjour! Comment aider votre {crop}?" # Version SMS courte
        
        return {
            "final_response": response,
            "execution_path": ["greeting"],
        }

    def route_to_message_flow_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Délègue au MessageFlow (multi-agents).

        IMPORTANT : on passe le state COMPLET au sous-graphe,
        pas une copie partielle (sinon on perd zone_id, crop, alerts, etc.).
        """
        logger.info("📨 Délégation au Message Flow (Conseil d'Experts)")

        try:
            # State COMPLET → le sous-graphe a accès à tout le contexte
            result = self.message_flow.graph.invoke(dict(state))

            return {
                "final_response": result.get("final_response", "Erreur de traitement"),
                "expert_responses": result.get("expert_responses", []),
                "audio_url": result.get("audio_url"),
                "execution_path": ["message_flow"],
            }

        except Exception as e:
            logger.warning("❌ Erreur MessageFlow: %s", e)
            return {
                "final_response": "Désolé, erreur technique. Réessayez ou contactez un conseiller.",
                "execution_path": ["message_flow_error"],
            }

    def route_to_report_flow_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Délègue au ReportFlow (rapports automatiques).

        IMPORTANT : on passe le state COMPLET au sous-graphe,
        le report_flow s'occupe du season_adapter + urgency_filter.
        """
        logger.info("📊 Délégation au Report Flow")

        try:
            result = self.report_flow.run(dict(state))

            return {
                "final_response": result.get("final_response", "Erreur rapport."),
                "final_report": result.get("final_report"),
                "execution_path": ["report_flow"],
            }

        except Exception as e:
            logger.warning("❌ Erreur ReportFlow: %s", e)
            return {
                "final_response": "Erreur rapport. Contactez 55555.",
                "execution_path": ["report_flow_error"],
            }

    def emergency_response_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        RÉPONSE URGENCE : Court-circuite le flow normal.

        Utilise EMERGENCY_RESPONSES (config module-level) au lieu de
        textes hardcodés dans le corps de la méthode.
        """
        logger.critical("🚨 MODE URGENCE ACTIVÉ")

        query = state.get("requete_utilisateur", "").lower()

        # Recherche dans la config par mot-clé
        response = EMERGENCY_RESPONSES["default"]
        for keyword in ["criquet", "sécheresse", "séchage"]:
            if keyword in query:
                key = "sécheresse" if keyword == "séchage" else keyword
                response = EMERGENCY_RESPONSES.get(key, response)
                break

        if state.get("is_sms_mode"):
            response = EMERGENCY_RESPONSES["sms"]

        return {
            "final_response": response,
            "execution_path": ["emergency_response"],
        }

    # ------------------------------------------------------------------ #
    # ROUTING LOGIC
    # ------------------------------------------------------------------ #

    def should_handle_emergency(self, state: GlobalAgriState) -> str:
        """Urgence? → Court-circuit tout."""
        alerts = state.get("global_alerts", [])
        if alerts and any(a["severity"] in [Severity.CRITICAL, Severity.HIGH] for a in alerts):
            return "emergency"
        return "normal"

    def route_by_flow_type(self, state: GlobalAgriState) -> str:
        """Quel type de réponse l'agriculteur attend?"""
        flow = state.get("flow_type", "MESSAGE")
        
        if flow == "GREETING":
            return "greeting"
        elif flow == "REPORT":
            return "report"
        else:
            return "message"

    # ------------------------------------------------------------------ #
    # GRAPH CONSTRUCTION
    # ------------------------------------------------------------------ #

    def _build_orchestrator_graph(self) -> StateGraph:
        """
        Graphe de décision principal.
        
        Flow:
        START → Triage → [Urgence? → Emergency | Normal → (Greeting|Message|Report)] → END
        """
        graph = StateGraph(GlobalAgriState)

        # Nœuds
        graph.add_node("triage", self.triage_node)
        graph.add_node("emergency", self.emergency_response_node)
        graph.add_node("greeting", self.greeting_node)
        graph.add_node("message_flow", self.route_to_message_flow_node)
        graph.add_node("report_flow", self.route_to_report_flow_node)

        # Routing
        graph.set_entry_point("triage")
        
        graph.add_conditional_edges(
            "triage",
            self.should_handle_emergency,
            {
                "emergency": "emergency",
                "normal": "route_normal"
            }
        )
        
        # Routing normal (pas d'urgence)
        graph.add_node("route_normal", lambda s: s)  # Pass-through node
        graph.add_conditional_edges(
            "route_normal",
            self.route_by_flow_type,
            {
                "greeting": "greeting",
                "message": "message_flow",
                "report": "report_flow"
            }
        )

        # Terminaisons
        graph.add_edge("emergency", END)
        graph.add_edge("greeting", END)
        graph.add_edge("message_flow", END)
        graph.add_edge("report_flow", END)

        return graph.compile()

    # ------------------------------------------------------------------ #
    # PUBLIC API
    # ------------------------------------------------------------------ #

    def process_user_request(
        self,
        user_query: str,
        user_id: str = "farmer_001",
        zone_id: str = "Koutiala",
        crop: str = "Maïs",
        is_sms_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Point d'entrée principal pour l'agriculteur.
        
        Args:
            user_query: La question/demande de l'agriculteur
            user_id: Identifiant agriculteur
            zone_id: Localisation (pour données météo/marché)
            crop: Culture principale
            is_sms_mode: Si True, réponse ultra-courte (<160 char)
        
        Returns:
            Dict avec:
                - final_response: La réponse à afficher
                - execution_path: Chemin d'exécution (debug)
                - global_alerts: Alertes éventuelles
        """
        logger.info(f"📞 Requête de {user_id} ({zone_id}): {user_query[:50]}...")
        
        initial_state = GlobalAgriState(
            requete_utilisateur=user_query,
            user_id=user_id,
            zone_id=zone_id,
            crop=crop,
            is_sms_mode=is_sms_mode,
            flow_type="MESSAGE",
            user_reliability_score=0.8,  # Default
            global_alerts=[],
            execution_path=[],
            final_response=None,
            needs=None,
            meteo_data=None,
            soil_data=None,
            health_data=None,
            market_data=None,
            health_raw_data=None,
            final_report=None
        )

        try:
            result = self.graph.invoke(initial_state)
            
            logger.info(f"✅ Réponse générée | Path: {result.get('execution_path')}")
            return {
                "final_response": result.get("final_response"),
                "execution_path": result.get("execution_path"),
                "global_alerts": result.get("global_alerts", []),
                "status": "SUCCESS"
            }
            
        except Exception as e:
            logger.warning(f"❌ Erreur orchestration: {e}", exc_info=True)
            fallback = (
                "Désolé, erreur technique. Contactez le 55555 pour assistance."
                if not is_sms_mode
                else "Erreur. Tel:55555"
            )
            return {
                "final_response": fallback,
                "execution_path": ["error"],
                "global_alerts": [],
                "status": "ERROR"
            }


# ======================================================================
# TESTS RAPIDES
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    orchestrator = AgribotMainOrchestrator()
    
    # Test 1: Salutation
    print("\n" + "="*60)
    print("TEST 1: Salutation")
    print("="*60)
    result = orchestrator.process_user_request("Bonjour", user_id="TestFarmer")
    print(f"Réponse: {result['final_response']}")
    print(f"Path: {result['execution_path']}")
    
    # Test 2: Urgence criquets
    print("\n" + "="*60)
    print("TEST 2: Urgence Criquets")
    print("="*60)
    result = orchestrator.process_user_request(
        "Invasion de criquets sur mes plants!",
        crop="Coton"
    )
    print(f"Réponse: {result['final_response']}")
    print(f"Alertes: {result['global_alerts']}")
    
    # Test 3: Question normale (SMS mode)
    print("\n" + "="*60)
    print("TEST 3: SMS Mode")
    print("="*60)
    result = orchestrator.process_user_request(
        "Quel est le prix du maïs?",
        is_sms_mode=True
    )
    print(f"Réponse: {result['final_response']}")
    print(f"Longueur: {len(result['final_response'])} caractères")
