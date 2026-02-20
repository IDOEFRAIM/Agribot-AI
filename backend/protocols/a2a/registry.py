"""
A2A Registry — Registre d'agents pour discovery et routing.
=============================================================

Chaque agent (interne ou externe) s'enregistre dans le registre avec
une "Agent Card" décrivant ses capacités, ses intents, et son endpoint.

Le registre permet :
  - Discovery : "Quels agents savent gérer SELL_PRODUCT ?"
  - Routing   : "Envoie ce message à l'agent qui gère la zone Bobo"
  - Health    : "L'agent X est-il disponible ?"
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger("A2A.Registry")


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BUSY = "busy"
    ERROR = "error"


class AgentDomain(str, Enum):
    DIAGNOSIS = "diagnosis"
    MARKET = "market"
    MARKETPLACE = "marketplace"
    WEATHER = "weather"
    FORMATION = "formation"
    SOIL = "soil"
    SCORING = "scoring"
    FINANCE = "finance"
    TRANSPORT = "transport"
    INVENTORY = "inventory"
    EXTERNAL = "external"


@dataclass
class AgentCard:
    """
    Carte d'identité d'un agent dans l'écosystème A2A.
    
    Équivalent de l'Agent Card du protocole Google A2A :
    un descripteur JSON qui permet aux autres agents de savoir
    ce que cet agent sait faire et comment lui parler.
    """
    agent_id: str = ""
    name: str = ""
    description: str = ""
    domain: AgentDomain = AgentDomain.EXTERNAL
    
    # Capacités
    intents: List[str] = field(default_factory=list)     # ["SELL_PRODUCT", "CHECK_PRICE"]
    capabilities: List[str] = field(default_factory=list) # ["text", "voice", "image"]
    zones: List[str] = field(default_factory=list)        # ["bobo", "ouaga", "all"]
    crops: List[str] = field(default_factory=list)        # ["mais", "coton", "all"]
    
    # Endpoint
    endpoint: str = ""          # URL ou adresse interne
    protocol: str = "internal"  # internal | http | grpc | websocket
    
    # Métadonnées
    version: str = "1.0"
    status: AgentStatus = AgentStatus.ACTIVE
    max_concurrent: int = 10    # Charge max simultanée
    avg_response_ms: int = 500  # Temps de réponse moyen
    
    registered_at: str = ""
    last_heartbeat: str = ""

    def __post_init__(self):
        if not self.agent_id:
            self.agent_id = str(uuid.uuid4())[:8]
        if not self.registered_at:
            self.registered_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["status"] = self.status.value
        return d

    def supports_intent(self, intent: str) -> bool:
        return intent.upper() in [i.upper() for i in self.intents]

    def supports_zone(self, zone: str) -> bool:
        return "all" in self.zones or zone.lower() in [z.lower() for z in self.zones]

    def supports_crop(self, crop: str) -> bool:
        return "all" in self.crops or crop.lower() in [c.lower() for c in self.crops]


class A2ARegistry:
    """
    Registre central des agents AgriConnect.
    
    Opérations :
      - register()    : Enregistre un agent avec sa carte
      - unregister()  : Retire un agent du registre
      - discover()    : Trouve les agents capables de gérer un intent/zone/crop
      - heartbeat()   : Met à jour le statut d'un agent
      - list_agents() : Liste tous les agents actifs
    
    Stockage : En mémoire (peut être migré vers Redis/PostgreSQL pour multi-instance).
    """

    def __init__(self):
        self._agents: Dict[str, AgentCard] = {}
        self._intent_index: Dict[str, List[str]] = {}  # intent → [agent_ids]
        self._zone_index: Dict[str, List[str]] = {}    # zone → [agent_ids]
        logger.info("🔌 A2A Registry initialisé")

    def register(self, card: AgentCard) -> str:
        """
        Enregistre un agent dans le registre.
        
        Returns:
            agent_id attribué
        """
        self._agents[card.agent_id] = card

        # Indexation par intent
        for intent in card.intents:
            intent_key = intent.upper()
            if intent_key not in self._intent_index:
                self._intent_index[intent_key] = []
            if card.agent_id not in self._intent_index[intent_key]:
                self._intent_index[intent_key].append(card.agent_id)

        # Indexation par zone
        for zone in card.zones:
            zone_key = zone.lower()
            if zone_key not in self._zone_index:
                self._zone_index[zone_key] = []
            if card.agent_id not in self._zone_index[zone_key]:
                self._zone_index[zone_key].append(card.agent_id)

        logger.info(
            "✅ Agent enregistré: %s (%s) — %d intents, %d zones",
            card.name, card.agent_id, len(card.intents), len(card.zones),
        )
        return card.agent_id

    def unregister(self, agent_id: str):
        """Retire un agent du registre."""
        card = self._agents.pop(agent_id, None)
        if card:
            # Nettoyage des index
            for intent_key, ids in self._intent_index.items():
                if agent_id in ids:
                    ids.remove(agent_id)
            for zone_key, ids in self._zone_index.items():
                if agent_id in ids:
                    ids.remove(agent_id)
            logger.info("❌ Agent retiré: %s (%s)", card.name, agent_id)

    def discover(
        self,
        intent: str = None,
        zone: str = None,
        crop: str = None,
        domain: AgentDomain = None,
        status: AgentStatus = AgentStatus.ACTIVE,
    ) -> List[AgentCard]:
        """
        Découvre les agents capables de traiter une requête.
        
        Filtrage multi-critères :
          - intent : L'agent sait-il gérer cet intent ?
          - zone   : L'agent couvre-t-il cette zone ?
          - crop   : L'agent connaît-il cette culture ?
          - domain : L'agent est-il dans ce domaine ?
          - status : L'agent est-il actif ?
        
        Returns:
            Liste d'AgentCards triée par pertinence
        """
        candidates = list(self._agents.values())

        # Filtre par status
        if status:
            candidates = [a for a in candidates if a.status == status]

        # Filtre par intent (index rapide)
        if intent:
            intent_key = intent.upper()
            if intent_key in self._intent_index:
                intent_ids = set(self._intent_index[intent_key])
                candidates = [a for a in candidates if a.agent_id in intent_ids]
            else:
                # Fallback : recherche dans les capacités
                candidates = [a for a in candidates if a.supports_intent(intent)]

        # Filtre par zone
        if zone:
            candidates = [a for a in candidates if a.supports_zone(zone)]

        # Filtre par culture
        if crop:
            candidates = [a for a in candidates if a.supports_crop(crop)]

        # Filtre par domaine
        if domain:
            candidates = [a for a in candidates if a.domain == domain]

        # Tri par temps de réponse (les plus rapides en premier)
        candidates.sort(key=lambda a: a.avg_response_ms)

        return candidates

    def heartbeat(self, agent_id: str, status: AgentStatus = AgentStatus.ACTIVE):
        """Met à jour le statut et le heartbeat d'un agent."""
        card = self._agents.get(agent_id)
        if card:
            card.status = status
            card.last_heartbeat = datetime.now(timezone.utc).isoformat()

    def list_agents(self, active_only: bool = True) -> List[AgentCard]:
        """Liste tous les agents du registre."""
        agents = list(self._agents.values())
        if active_only:
            agents = [a for a in agents if a.status == AgentStatus.ACTIVE]
        return agents

    def get_agent(self, agent_id: str) -> Optional[AgentCard]:
        """Récupère la carte d'un agent par ID."""
        return self._agents.get(agent_id)

    def stats(self) -> Dict[str, Any]:
        """Statistiques du registre."""
        agents = list(self._agents.values())
        return {
            "total_agents": len(agents),
            "active": sum(1 for a in agents if a.status == AgentStatus.ACTIVE),
            "intents_indexed": len(self._intent_index),
            "zones_indexed": len(self._zone_index),
            "domains": list(set(a.domain.value for a in agents)),
        }
