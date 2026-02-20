"""
A2A Messaging — Système de messages inter-agents.
===================================================

Chaque agent peut envoyer et recevoir des messages A2A structurés.
Les messages sont routés via le registre (discovery) ou en point-à-point.

Types de messages :
  - REQUEST    : Demande d'action (ex: "Vends 5 tonnes de maïs")
  - RESPONSE   : Réponse à une demande
  - BROADCAST  : Diffusion (ex: offre de vente)
  - SUBSCRIBE  : Abonnement à un type d'offre
  - HANDSHAKE  : Négociation entre agents (ex: prix, conditions)
  - HEARTBEAT  : Signal de présence
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
from collections import defaultdict

logger = logging.getLogger("A2A.Messaging")


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    HANDSHAKE = "handshake"
    HEARTBEAT = "heartbeat"
    ACK = "ack"


class HandshakeStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTER = "counter_offer"
    COMPLETED = "completed"


@dataclass
class A2AMessage:
    """
    Message inter-agents standardisé.
    
    Un message A2A transporte :
      - L'identité de l'émetteur/destinataire
      - Le type de message
      - Le payload structuré
      - Les métadonnées de traçabilité
    """
    message_id: str = ""
    message_type: MessageType = MessageType.REQUEST
    
    # Parties
    sender_id: str = ""
    receiver_id: str = ""  # Vide pour BROADCAST
    
    # Contenu
    intent: str = ""          # SELL_PRODUCT, BUY_PRODUCT, CHECK_PRICE...
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # Négociation (pour HANDSHAKE)
    handshake_status: Optional[HandshakeStatus] = None
    reference_id: str = ""    # ID du message initial (pour réponses/contre-offres)
    
    # Métadonnées
    zone: str = ""
    crop: str = ""
    priority: int = 0         # 0=normal, 1=high, 2=urgent
    ttl: int = 3600           # Time-to-live en secondes
    
    created_at: str = ""
    expires_at: str = ""
    
    # Token Economy & Idempotence
    idempotency_key: str = ""    # Clé unique pour éviter les doublons
    schema_version: str = "1.0"  # Versioning du format

    def __post_init__(self):
        if not self.message_id:
            self.message_id = str(uuid.uuid4())[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.idempotency_key:
            # Clé dérivée de sender+intent+payload hash pour déduplication
            import hashlib
            raw = f"{self.sender_id}:{self.intent}:{json.dumps(self.payload, sort_keys=True, default=str)}"
            self.idempotency_key = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def validate(self) -> Dict[str, Any]:
        """
        Contrat d'interface strict — rejette les messages mal formés.
        Retourne {"status": "ok"} ou {"error": "INVALID_MESSAGE", "details": [...]}.
        """
        errors = []
        if not self.sender_id:
            errors.append("sender_id requis")
        if not self.intent:
            errors.append("intent requis")
        if self.message_type == MessageType.HANDSHAKE and not self.handshake_status:
            errors.append("handshake_status requis pour HANDSHAKE")
        if self.message_type == MessageType.RESPONSE and not self.reference_id:
            errors.append("reference_id requis pour RESPONSE")
        if errors:
            return {"error": "INVALID_MESSAGE", "details": errors}
        return {"status": "ok"}

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["message_type"] = self.message_type.value
        if self.handshake_status:
            d["handshake_status"] = self.handshake_status.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def create_response(self, payload: Dict[str, Any], status: str = "ok") -> "A2AMessage":
        """Crée un message de réponse à ce message."""
        return A2AMessage(
            message_type=MessageType.RESPONSE,
            sender_id=self.receiver_id,
            receiver_id=self.sender_id,
            intent=self.intent,
            payload={**payload, "status": status},
            reference_id=self.message_id,
            zone=self.zone,
            crop=self.crop,
        )

    def create_counter_offer(self, counter_payload: Dict[str, Any]) -> "A2AMessage":
        """Crée une contre-offre dans un handshake."""
        return A2AMessage(
            message_type=MessageType.HANDSHAKE,
            sender_id=self.receiver_id,
            receiver_id=self.sender_id,
            intent=self.intent,
            payload=counter_payload,
            handshake_status=HandshakeStatus.COUNTER,
            reference_id=self.message_id,
            zone=self.zone,
            crop=self.crop,
        )


class A2AChannel:
    """
    Canal de communication A2A.
    
    Gère :
      - La file de messages (in-memory, migreable vers Redis/RabbitMQ)
      - Le routing (point-à-point et broadcast)
      - Les abonnements (subscribe/unsubscribe)
      - Le handshake (négociation multi-tours)
    
    Pour la scalabilité nationale, ce canal peut être remplacé
    par Redis Pub/Sub ou RabbitMQ sans changer l'API.
    """

    def __init__(self):
        self._queues: Dict[str, List[A2AMessage]] = defaultdict(list)     # agent_id → messages
        self._subscriptions: Dict[str, List[str]] = defaultdict(list)     # topic → [agent_ids]
        self._handlers: Dict[str, Callable] = {}                          # agent_id → callback
        self._handshakes: Dict[str, List[A2AMessage]] = defaultdict(list) # handshake_id → messages
        self._message_log: List[A2AMessage] = []                          # Audit trail
        self._seen_idempotency: set = set()                               # Idempotence dedup
        logger.info("🔌 A2A Channel initialisé")

    # ═══════════════════════════════════════════════════════════
    # ENVOI DE MESSAGES
    # ═══════════════════════════════════════════════════════════

    def send(self, message: A2AMessage) -> str:
        """
        Envoie un message à un agent spécifique.
        Valide le contrat, déduplique par idempotency_key.
        
        Returns:
            message_id du message envoyé
        """
        # Contrat d'interface strict
        validation = message.validate()
        if validation.get("error"):
            logger.warning("A2A message rejeté: %s", validation)
            return ""

        if not message.receiver_id:
            raise ValueError("receiver_id requis pour send(). Utiliser broadcast() pour diffusion.")

        # Idempotence : ignorer les doublons
        if message.idempotency_key in self._seen_idempotency:
            logger.debug("A2A doublon ignoré: %s", message.idempotency_key)
            return message.message_id
        self._seen_idempotency.add(message.idempotency_key)

        self._queues[message.receiver_id].append(message)
        self._message_log.append(message)

        # Callback si enregistré
        handler = self._handlers.get(message.receiver_id)
        if handler:
            try:
                handler(message)
            except Exception as e:
                logger.error("A2A handler error for %s: %s", message.receiver_id, e)

        logger.debug(
            "📨 A2A: %s → %s [%s] %s",
            message.sender_id, message.receiver_id,
            message.message_type.value, message.intent,
        )
        return message.message_id

    def broadcast(self, message: A2AMessage, topic: str = None) -> List[str]:
        """
        Diffuse un message à tous les agents abonnés à un topic.
        
        Args:
            message: Message à diffuser
            topic: Topic de diffusion (ex: "SELL_MAIS_BOBO")
            
        Returns:
            Liste des agent_ids qui ont reçu le message
        """
        message.message_type = MessageType.BROADCAST
        delivered_to = []

        # Topic-based broadcast
        if topic:
            subscribers = self._subscriptions.get(topic, [])
            for agent_id in subscribers:
                if agent_id != message.sender_id:  # Pas d'auto-envoi
                    msg_copy = A2AMessage(**{**asdict(message), "receiver_id": agent_id, "message_id": str(uuid.uuid4())[:12]})
                    self._queues[agent_id].append(msg_copy)
                    delivered_to.append(agent_id)

        # Intent + Zone based broadcast (auto-topic)
        if message.intent and message.zone:
            auto_topic = f"{message.intent}_{message.zone}".upper()
            auto_subs = self._subscriptions.get(auto_topic, [])
            for agent_id in auto_subs:
                if agent_id not in delivered_to and agent_id != message.sender_id:
                    msg_copy = A2AMessage(**{**asdict(message), "receiver_id": agent_id, "message_id": str(uuid.uuid4())[:12]})
                    self._queues[agent_id].append(msg_copy)
                    delivered_to.append(agent_id)

        self._message_log.append(message)
        logger.info("📡 A2A Broadcast [%s]: %d agents", topic or message.intent, len(delivered_to))
        return delivered_to

    # ═══════════════════════════════════════════════════════════
    # RÉCEPTION ET ABONNEMENTS
    # ═══════════════════════════════════════════════════════════

    def receive(self, agent_id: str, limit: int = 10) -> List[A2AMessage]:
        """Récupère les messages en attente pour un agent."""
        messages = self._queues[agent_id][:limit]
        self._queues[agent_id] = self._queues[agent_id][limit:]
        return messages

    def subscribe(self, agent_id: str, topic: str):
        """Abonne un agent à un topic."""
        if agent_id not in self._subscriptions[topic]:
            self._subscriptions[topic].append(agent_id)
            logger.info("📌 %s abonné à [%s]", agent_id, topic)

    def unsubscribe(self, agent_id: str, topic: str):
        """Désabonne un agent d'un topic."""
        if agent_id in self._subscriptions[topic]:
            self._subscriptions[topic].remove(agent_id)

    def register_handler(self, agent_id: str, handler: Callable):
        """Enregistre un callback pour réception temps réel."""
        self._handlers[agent_id] = handler


    # ═══════════════════════════════════════════════════════════
    # HANDSHAKE (NÉGOCIATION) AVEC TIMEOUT & FALLBACK
    # ═══════════════════════════════════════════════════════════

    def initiate_handshake(self, message: A2AMessage, max_turns: int = 5, timeout: int = 300) -> str:
        """
        Initie une négociation entre deux agents avec Timeout et Limite de tours.
        
        Args:
            message: Message initial (PROPOSED)
            max_turns: Nombre max d'allers-retours avant échec
            timeout: Durée max en secondes avant expiration
        """
        message.message_type = MessageType.HANDSHAKE
        message.handshake_status = HandshakeStatus.PROPOSED
        # Métadonnées de contrôle
        message.payload["_control"] = {
            "max_turns": max_turns,
            "turns_count": 0,
            "timeout_at": (datetime.now(timezone.utc).timestamp() + timeout)
        }
        
        handshake_id = message.message_id
        self._handshakes[handshake_id].append(message)
        
        # Envoi initial
        self.send(message)

        logger.info(
            "🤝 Handshake initié [%s]: %s → %s (Max turns: %d)",
            handshake_id, message.sender_id, message.receiver_id, max_turns,
        )
        return handshake_id

    def respond_handshake(
        self,
        handshake_id: str,
        responder_id: str,
        status: HandshakeStatus,
        payload: Dict[str, Any] = None,
    ) -> A2AMessage:
        """
        Répond à un handshake en cours avec vérification des limites.
        """
        history = self._handshakes.get(handshake_id, [])
        if not history:
            raise ValueError(f"Handshake {handshake_id} introuvable")

        last_msg = history[-1]
        
        # 1. Vérification Timeout
        control = last_msg.payload.get("_control", {})
        timeout_at = control.get("timeout_at", 0)
        if timeout_at and datetime.now(timezone.utc).timestamp() > timeout_at:
            logger.warning(f"⏳ Handshake {handshake_id} expiré (Timeout)")
            return self._finalize_handshake(handshake_id, responder_id, HandshakeStatus.REJECTED, {"reason": "TIMEOUT"})

        # 2. Vérification Max Turns
        current_turns = control.get("turns_count", 0)
        if current_turns >= control.get("max_turns", 5):
            logger.warning(f"🔄 Handshake {handshake_id} annulé (Max turns exceeded)")
            return self._finalize_handshake(handshake_id, responder_id, HandshakeStatus.REJECTED, {"reason": "MAX_TURNS_EXCEEDED"})

        # Mise à jour du compteur
        new_payload = payload or {}
        new_payload["_control"] = control
        new_payload["_control"]["turns_count"] = current_turns + 1

        response = A2AMessage(
            message_type=MessageType.HANDSHAKE,
            sender_id=responder_id,
            receiver_id=last_msg.sender_id,
            intent=last_msg.intent,
            payload=new_payload,
            handshake_status=status,
            reference_id=handshake_id,
            zone=last_msg.zone,
            crop=last_msg.crop,
        )

        self._handshakes[handshake_id].append(response)
        self.send(response)

        if status == HandshakeStatus.ACCEPTED:
            logger.info("✅ Handshake accepté [%s]", handshake_id)
        elif status == HandshakeStatus.REJECTED:
            logger.info("❌ Handshake rejeté [%s]", handshake_id)

        return response

    def _finalize_handshake(self, handshake_id, sender_id, status, payload):
        """Force la fin d'un handshake (timeout/error)."""
        last_msg = self._handshakes[handshake_id][-1]
        final_msg = A2AMessage(
            message_type=MessageType.HANDSHAKE,
            sender_id=sender_id,
            receiver_id=last_msg.sender_id, # Retour à l'envoyeur précédent
            intent=last_msg.intent,
            payload=payload,
            handshake_status=status,
            reference_id=handshake_id
        )
        self._handshakes[handshake_id].append(final_msg)
        self.send(final_msg)
        return final_msg

    def get_handshake_history(self, handshake_id: str) -> List[A2AMessage]:
        """Retourne l'historique complet d'un handshake."""
        return self._handshakes.get(handshake_id, [])

    # ═══════════════════════════════════════════════════════════
    # MONITORING
    # ═══════════════════════════════════════════════════════════

    def stats(self) -> Dict[str, Any]:
        """Statistiques du canal."""
        return {
            "pending_messages": sum(len(q) for q in self._queues.values()),
            "active_subscriptions": sum(len(s) for s in self._subscriptions.values()),
            "total_messages_sent": len(self._message_log),
            "active_handshakes": sum(
                1 for h in self._handshakes.values()
                if h and h[-1].handshake_status not in (HandshakeStatus.COMPLETED, HandshakeStatus.REJECTED)
            ),
            "queues": {k: len(v) for k, v in self._queues.items() if v},
        }
