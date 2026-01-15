import os
import logging
from celery import Celery
from orchestrator.message_flow import MessageResponseFlow
from orchestrator.state import GlobalAgriState
from utils.sms_adapter import SMSAdapter

# Configuration du Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AgriConnect_Worker")

# Configuration Celery
# En local on utilise Redis, en Prod sur AWS on utilisera SQS
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery_app = Celery(
    "agriconnect_worker",
    broker=BROKER_URL,
    backend=BACKEND_URL
)

# Initialisation unique de l'orchestrateur pour ce worker
# (Évite de recharger le LLM à chaque requête -> Gain de performance énorme)
try:
    flow_instance = MessageResponseFlow().build_graph()
    logger.info("✅ Worker IA initialisé et prêt.")
except Exception as e:
    logger.error(f"❌ Erreur init Worker: {e}")
    flow_instance = None

@celery_app.task(name="process_user_query", bind=True, max_retries=3)
def process_user_query(self, state: GlobalAgriState):
    """
    Tâche asynchrone qui exécute l'IA.
    Si ça plante (ex: API météo HS), ça réessaie 3 fois automatiquement.
    """
    logger.info(f"⚙️ Traitement tâche pour User {state.get('user_id')}")
    
    try:
        if not flow_instance:
            raise Exception("L'orchestrateur n'est pas chargé.")

        # Exécution du Graphe LangGraph
        result = flow_instance.invoke(state)
        final_response = result.get("final_response", "Erreur de traitement.")
        
        # ICI : Envoi de la réponse (Push Notification ou SMS API)
        # Dans un vrai système asynchrone, on ne "return" pas au client HTTP,
        # on appelle l'API d'envoi de SMS (Twilio/Orange) pour répondre proactivement.
        
        # Simulation d'envoi SMS
        if state.get("is_sms_mode"):
            sms_content = SMSAdapter.compress_for_sms(final_response)
            logger.info(f"📤 ENVOI SMS vers {state.get('user_id')}: {sms_content}")
            # send_sms_via_orange(state['user_id'], sms_content)
            return sms_content
            
        return final_response

    except Exception as e:
        logger.error(f"Erreur Worker: {e}")
        # Réessaie dans 5 secondes en cas d'échec
        raise self.retry(exc=e, countdown=5)
