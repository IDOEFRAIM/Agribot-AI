import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from orchestrator.main_orchestrator import MainOrchestrator
from orchestrator.state import GlobalAgriState
from utils.sms_adapter import SMSAdapter
# Import du système de Queue (Celery)
# Note: Si Celery n'est pas lancé, assurez-vous de gérer l'erreur ou d'avoir un fallback
try:
    from backend.worker import process_user_query
    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False
    
# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AgConnectAPI")

app = FastAPI(title="AgConnect API", description="Agricultural Assistant Backend", version="1.0.0")

# Initialize Direct Orchestrator (Fallback Synchrone)
try:
    orchestrator_instance = MainOrchestrator()
    logger.info("✅ Orchestrator (Direct) initialized successfully.")
except Exception as e:
    logger.error(f"❌ Failed to initialize Orchestrator: {e}")
    # En prod, on ne raise pas forcément si on compte sur le worker, mais pour le dev, c'est mieux
    # raise e 

class UserRequest(BaseModel):
    user_id: str = "user_123"
    zone_id: str = "Centre"
    query: Optional[str] = ""
    flow_type: str = "MESSAGE" # MESSAGE or REPORT
    async_mode: bool = False # Option pour forcer le mode async

class SMSData(BaseModel):
    from_number: str
    text: str

@app.post("/api/v1/sms/hook")
async def sms_webhook(data: SMSData):
    """
    Endpoint SMS Asynchrone (Pilier 4 - Scalabilité).
    Accepte : { "from_number": "+226...", "text": "PLUIE OUAGA" }
    """
    logger.info(f"📱 SMS received from {data.from_number}: {data.text}")
    
    # 1. Adaptateur
    formatted = SMSAdapter.format_incoming_sms(data.text, data.from_number)
    
    # 2. State
    state: GlobalAgriState = {
        "requete_utilisateur": formatted["query"],
        "zone_id": "unknown", 
        "user_id": formatted["user_id"],
        "flow_type": "MESSAGE",
        "is_sms_mode": True,
        "user_reliability_score": 0.5
    }
    
    # 3. Mode Asynchrone (Recommandé pour la charge)
    if ASYNC_AVAILABLE:
        # On met le message dans la file d'attente Redis/SQS
        task = process_user_query.delay(state)
        logger.info(f"🚀 Tâche envoyée au worker: {task.id}")
        return {"status": "RECEIVED", "task_id": task.id, "message": "Traitement en cours... Vous recevrez un SMS."}
    
    # 4. Fallback Synchrone (Si pas de worker lancé)
    try:
        result = orchestrator_instance.run(state)
        response_text = result.get("final_response", "Erreur système.")
        sms_response = SMSAdapter.compress_for_sms(response_text)
        return {"message": sms_response}
    except Exception as e:
        logger.error(f"Sync Processing Error: {e}")
        return {"message": "Service indisponible."}
        "flow_type": "MESSAGE",
        "is_sms_mode": True,
        "user_reliability_score": 0.5
    }
    
    # 3. Execution
    try:
        result = orchestrator_instance.run(state)
        response_text = result.get("final_response", "Erreur système.")
        
        # 4. Compression
        sms_response = SMSAdapter.compress_for_sms(response_text)
        return {"message": sms_response} # Twilio/AfricasTalking attendent souvent du XML ou PlainText, ici JSON pour standard
    except Exception as e:
        logger.error(f"SMS Processing Error: {e}")
        return {"message": "Service indisponible. Réessayez plus tard."}

@app.post("/api/v1/ask")
async def ask_agent(req: UserRequest):
    """
    Main endpoint to interact with the AgConnect Orchestrator.
    Handles both conversational queries (MESSAGE) and report generation (REPORT).
    """
    logger.info(f"📨 Received request: flow={req.flow_type}, query='{req.query}'")
    
    # Construct Initial State based on GlobalAgriState definition
    initial_state: GlobalAgriState = {
        "requete_utilisateur": req.query, 
        "zone_id": req.zone_id,
        "flow_type": req.flow_type,
        "execution_path": [],
        # Initialize empty data containers
        "meteo_data": {},
        "market_data": {},
        "user_profile": {"id": req.user_id}
    }
    
    try:
        # Run Orchestrator
        result = orchestrator_instance.run(initial_state)
        
        # Extract relevant response based on flow type
        final_output = ""
        if req.flow_type == "MESSAGE":
            final_output = result.get("final_response", "Je n'ai pas pu générer de réponse.")
        elif req.flow_type == "REPORT":
            report_data = result.get("final_report", {})
            final_output = report_data.get("content", "Rapport vide.")
        
        print('respponse',final_output)
        return {
            "status": "success",
            "response": final_output,
            "trace": result.get("execution_path", []) 
        }
            
    except Exception as e:
        logger.error(f"❌ Orchestrator execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "active", "component": "AgConnect Backend"}

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
