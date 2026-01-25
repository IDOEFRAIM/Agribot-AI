import logging
import json
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("AlertReporter")

class AlertReporter:
    """
    Outil collaboratif permettant aux agriculteurs de signaler des problèmes (Pilier 1 - Sentinelle).
    Les alertes sont stockées et nécessitent une validation si critique.
    """
    
    def __init__(self, db_path="events_log.json"):
        self.db_path = db_path
        # Simulation d'une DB en mémoire pour la démo
        self.events = []

    def report_event(self, user_id: str, zone_id: str, description: str, event_type: str = "UNKNOWN") -> Dict[str, Any]:
        """
        Enregistre un signalement terrain.
        """
        # 1. Analyse basique de gravité (pourrait être faite par LLM)
        severity = "MEDIUM"
        if any(x in description.lower() for x in ["inondation", "feu", "envahisseur", "criquet", "mort"]):
            severity = "CRITICAL"
        elif any(x in description.lower() for x in ["chenille", "maladie", "jaunisse"]):
            severity = "HIGH"

        # 2. Création de l'événement
        event = {
            "id": f"EVT-{int(time.time())}",
            "timestamp": time.time(),
            "user_id": user_id,
            "zone": zone_id,
            "type": event_type,
            "description": description,
            "severity": severity,
            "status": "PENDING_VALIDATION" if severity == "CRITICAL" else "VERIFIED"
        }
        
        self.events.append(event)
        logger.info(f"🚨 NOUVELLE ALERTE REÇUE [{severity}]: {description}")
        
        # 3. Logique de feedback immédiat
        if severity == "CRITICAL":
            return {
                "response": "🚨 ALERTE REÇUE. Un expert va valider cette information d'urgence. Mettez-vous en sécurité.",
                "requires_human_validation": True,
                "alert_id": event["id"]
            }
        else:
            trust_reward = 5 # Points de confiance gagnés
            return {
                "response": f"Merci pour ce signalement. Il a été partagé avec la communauté de {zone_id}. (+{trust_reward} pts confiance)",
                "requires_human_validation": False,
                "trust_score_update": trust_reward
            }

    def get_recent_alerts(self, zone_id: str) -> List[Dict]:
        """Récupère les alertes valides d'une zone."""
        return [e for e in self.events if e["zone"] == zone_id and e["status"] == "VERIFIED"]
