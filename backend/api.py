# api.py
import os
import sys

# Ajoute le dossier parent (AgConnect) au sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)
    
import logging
from flask import Flask, request, jsonify
from utils.sms_adapter import SMSAdapter # Import du PILIER 4

# Import de ton orchestrateur
from orchestrator import AgriculturalOrchestrator, OrchestratorState

# Initialisation Flask
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Initialisation de l'orchestrateur + graphe
orchestrator = AgriculturalOrchestrator()
graph = orchestrator.get_graph()

# --- Middleware SMS (Omnicanalité) ---
@app.route("/api/v1/sms/hook", methods=["POST"])
def sms_webhook():
    """
    Endpoint optimisé pour les passerelles SMS/USSD (Twilio, AfricasTalking, Orange API).
    Accepte : { "from": "+226...", "text": "PLUIE OUAGA" }
    Retourne : Texte brut < 160 chars.
    """
    data = request.get_json() or request.form
    sender = data.get("from") or data.get("sender")
    text = data.get("text") or data.get("message")
    
    if not text:
        return "ERR: Message vide", 400
        
    # 1. Adaptation de l'entrée (Formatage)
    formatted_input = SMSAdapter.format_incoming_sms(text, sender)
    
    # Construction de l'état
    state: OrchestratorState = {
        "zone_id": "unknown", # Sera déduit ou géré par l'agent
        "requete_utilisateur": formatted_input["query"],
        "user_id": formatted_input["user_id"],
        "flow_type": "MESSAGE",
        "is_sms_mode": True # Active le mode concis
    }
    
    try:
        # 2. Exécution du workflow
        # Note: On suppose que orchestrator.run() est compatible, sinon on appelle graph.invoke(state)
        # Adaptation selon ton main_orchestrator.py qui a une méthode .run()
        # Ici on utilise directement le graph si possible ou l'instance wrapper
        if hasattr(orchestrator, 'run'):
            # Si MainOrchestrator a une méthode run
            result = orchestrator.run(state)
        else:
            # Fallback direct sur le graphe
            result = graph.invoke(state)
            
        full_response = result.get("final_response", "Service indisponible.")
        
        # 3. Compression de la sortie (SMS < 160 chars)
        sms_response = SMSAdapter.compress_for_sms(full_response)
        
        return sms_response, 200, {'Content-Type': 'text/plain'}

    except Exception as e:
        logging.error(f"SMS Error: {e}")
        return "ERR: Service momentanement indisponible.", 200


@app.route("/api/ask", methods=["POST"])
def ask():
    """
    Endpoint principal :
    {
        "user_id": "123",
        "zone_id": "Mopti",
        "query": "Mon sol est sableux, que faire ?"
    }
    """
    try:
        data = request.get_json()

        if not data or "query" not in data:
            return jsonify({"error": "Champ 'query' manquant"}), 400

        user_id = data.get("user_id", "anonymous")
        zone_id = data.get("zone_id", "ouaga")
        query = data["query"]

        # Construction de l'état initial
        state: OrchestratorState = {
            "user_id": user_id,
            "zone_id": zone_id,
            "user_query": query,
            "intent": "",
            "context_data": {},
            "final_response": "",
            "execution_trace": [],
            "meteo_data": None,
            "culture_config": None,
            "soil_config": None,
            "user_profile": None
        }

        # Exécution du graphe LangGraph
        result = graph.invoke(state)

        print(result)
        return jsonify({
            "response": result["final_response"],
            "intent": result["intent"],
            "trace": result["execution_trace"]
        })

    except Exception as e:
        logging.exception("Erreur API")
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "API Agricole opérationnelle ✅"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)