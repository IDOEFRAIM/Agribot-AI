"""
A2A Discovery — Service de découverte d'agents pour AgriConnect.
=================================================================

Combine le registre (Registry) et le canal (Channel) pour fournir
un mécanisme complet de discovery et routing :

  1. Un agent PUBLIE ses capacités (Register)
  2. Un autre agent CHERCHE qui peut traiter son intent (Discover)
  3. Il ENVOIE un message au(x) agent(s) trouvé(s) (Route)

Ce service est le point d'entrée unique pour toute communication A2A.
"""

import logging
from typing import Any, Dict, List, Optional

from .registry import A2ARegistry, AgentCard, AgentDomain, AgentStatus
from .messaging import A2AChannel, A2AMessage, MessageType, HandshakeStatus

logger = logging.getLogger("A2A.Discovery")


class A2ADiscovery:
    """
    Service de découverte et routing inter-agents.
    
    Usage :
        discovery = A2ADiscovery()
        
        # Enregistrer les agents internes
        discovery.register_internal_agents()
        
        # Trouver un agent capable de gérer SELL_PRODUCT à Bobo
        agents = discovery.find_agents(intent="SELL_PRODUCT", zone="bobo")
        
        # Envoyer une offre de vente
        discovery.route_message(
            sender="marketplace_001",
            intent="SELL_PRODUCT",
            payload={"product": "mais", "quantity_kg": 5000, "price_fcfa": 225},
            zone="bobo",
        )
    """

    def __init__(self, registry: A2ARegistry = None, channel: A2AChannel = None):
        self.registry = registry or A2ARegistry()
        self.channel = channel or A2AChannel()
        logger.info("🔌 A2A Discovery Service initialisé")

    # ═══════════════════════════════════════════════════════════
    # ENREGISTREMENT DES AGENTS INTERNES
    # ═══════════════════════════════════════════════════════════

    def register_internal_agents(self):
        """
        Enregistre les 5 agents internes d'AgriConnect dans le registre A2A.
        Appelé au démarrage de l'orchestrateur.
        """
        internal_agents = [
            AgentCard(
                agent_id="plant_doctor",
                name="PlantDoctor",
                description="Diagnostic phytosanitaire et recommandations de traitement",
                domain=AgentDomain.DIAGNOSIS,
                intents=["DIAGNOSE", "IDENTIFY_DISEASE", "RECOMMEND_TREATMENT", "CHECK_SYMPTOM"],
                capabilities=["text", "image", "voice"],
                zones=["all"],
                crops=["all"],
                protocol="internal",
                avg_response_ms=800,
            ),
            AgentCard(
                agent_id="market_coach",
                name="MarketCoach",
                description="Analyse de marché, prix et conseil de vente",
                domain=AgentDomain.MARKET,
                intents=["CHECK_PRICE", "SELL_OFFER", "BUY_OFFER", "SCAM_CHECK", "MARKET_ANALYSIS"],
                capabilities=["text", "voice"],
                zones=["ouagadougou", "bobo-dioulasso", "koudougou", "ouahigouya", "kaya", "banfora", "pouytenga", "fada"],
                crops=["all"],
                protocol="internal",
                avg_response_ms=600,
            ),
            AgentCard(
                agent_id="formation_coach",
                name="FormationCoach",
                description="Formation agricole et conseil technique",
                domain=AgentDomain.FORMATION,
                intents=["LEARN", "HOW_TO", "BEST_PRACTICE", "TRAINING_MODULE"],
                capabilities=["text", "voice"],
                zones=["all"],
                crops=["all"],
                protocol="internal",
                avg_response_ms=700,
            ),
            AgentCard(
                agent_id="climate_sentinel",
                name="ClimateSentinel",
                description="Veille climatique, alertes météo et conseil agrométéo",
                domain=AgentDomain.WEATHER,
                intents=["CHECK_WEATHER", "GET_ALERT", "FLOOD_RISK", "SATELLITE_DATA", "AGRO_METEO"],
                capabilities=["text", "voice", "map"],
                zones=["all"],
                crops=["all"],
                protocol="internal",
                avg_response_ms=500,
            ),
            AgentCard(
                agent_id="marketplace_agent",
                name="MarketplaceAgent",
                description="Gestion stocks, annonces, matching acheteur-vendeur",
                domain=AgentDomain.MARKETPLACE,
                intents=[
                    "REGISTER_STOCK", "SELL_PRODUCT", "BUY_PRODUCT",
                    "CHECK_STOCK", "CHECK_ORDERS", "FIND_BUYERS",
                    "FIND_PRODUCTS", "CREATE_ORDER", "MATCH_OFFER",
                ],
                capabilities=["text", "voice", "transaction"],
                zones=["all"],
                crops=["all"],
                protocol="internal",
                avg_response_ms=600,
            ),
        ]

        for card in internal_agents:
            self.registry.register(card)

            # Auto-abonnement aux topics pertinents
            for intent in card.intents:
                self.channel.subscribe(card.agent_id, intent.upper())
                for zone in card.zones:
                    if zone != "all":
                        self.channel.subscribe(card.agent_id, f"{intent}_{zone}".upper())

        logger.info("✅ %d agents internes enregistrés", len(internal_agents))

    def register_external_agent(self, card: AgentCard) -> str:
        """
        Enregistre un agent externe (banque, transporteur, SONAGESS...).
        
        Args:
            card: Carte de l'agent externe
            
        Returns:
            agent_id attribué
        """
        card.protocol = card.protocol or "http"
        agent_id = self.registry.register(card)

        for intent in card.intents:
            self.channel.subscribe(card.agent_id, intent.upper())

        logger.info("🔗 Agent externe enregistré: %s (%s)", card.name, card.endpoint)
        return agent_id

    # ═══════════════════════════════════════════════════════════
    # DISCOVERY
    # ═══════════════════════════════════════════════════════════

    def find_agents(
        self,
        intent: str = None,
        zone: str = None,
        crop: str = None,
        domain: AgentDomain = None,
    ) -> List[AgentCard]:
        """
        Trouve les agents capables de traiter une requête.
        
        Args:
            intent: Intent à traiter (ex: "SELL_PRODUCT")
            zone: Zone géographique
            crop: Culture concernée
            domain: Domaine métier
            
        Returns:
            Liste d'AgentCards triée par pertinence
        """
        return self.registry.discover(intent=intent, zone=zone, crop=crop, domain=domain)

    # ═══════════════════════════════════════════════════════════
    # ROUTING
    # ═══════════════════════════════════════════════════════════

    def route_message(
        self,
        sender: str,
        intent: str,
        payload: Dict[str, Any],
        zone: str = "",
        crop: str = "",
        receiver: str = None,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """
        Route un message vers le(s) agent(s) approprié(s).
        
        Si receiver est spécifié : envoi point-à-point.
        Sinon : discovery automatique + envoi au meilleur agent.
        
        Returns:
            {"message_id": "...", "delivered_to": [...], "status": "ok|no_agent"}
        """
        message = A2AMessage(
            sender_id=sender,
            intent=intent,
            payload=payload,
            zone=zone,
            crop=crop,
            priority=priority,
        )

        # Envoi point-à-point
        if receiver:
            message.receiver_id = receiver
            msg_id = self.channel.send(message)
            return {"message_id": msg_id, "delivered_to": [receiver], "status": "ok"}

        # Discovery + routing automatique
        agents = self.find_agents(intent=intent, zone=zone, crop=crop)
        if not agents:
            logger.warning("🚫 Aucun agent trouvé pour intent=%s zone=%s", intent, zone)
            return {"message_id": message.message_id, "delivered_to": [], "status": "no_agent"}

        # Envoi au meilleur agent (le plus rapide)
        best = agents[0]
        message.receiver_id = best.agent_id
        msg_id = self.channel.send(message)

        return {
            "message_id": msg_id,
            "delivered_to": [best.agent_id],
            "agent_name": best.name,
            "status": "ok",
        }

    def broadcast_offer(
        self,
        sender: str,
        intent: str,
        payload: Dict[str, Any],
        zone: str = "",
        crop: str = "",
    ) -> Dict[str, Any]:
        """
        Diffuse une offre (vente/achat) à tous les agents intéressés.
        
        Usage typique : Agent Marketplace diffuse "5 tonnes de maïs disponibles à Bobo"
        Tous les agents abonnés à SELL_PRODUCT_BOBO reçoivent le message.
        """
        message = A2AMessage(
            sender_id=sender,
            intent=intent,
            payload=payload,
            zone=zone,
            crop=crop,
        )

        topic = f"{intent}_{zone}".upper() if zone else intent.upper()
        delivered = self.channel.broadcast(message, topic=topic)

        return {
            "message_id": message.message_id,
            "topic": topic,
            "delivered_to": delivered,
            "count": len(delivered),
            "status": "ok",
        }

    def initiate_trade(
        self,
        seller_id: str,
        buyer_id: str,
        offer: Dict[str, Any],
        zone: str = "",
        crop: str = "",
    ) -> str:
        """
        Initie un handshake de négociation entre un vendeur et un acheteur.
        
        Returns:
            handshake_id pour suivi
        """
        message = A2AMessage(
            sender_id=seller_id,
            receiver_id=buyer_id,
            intent="TRADE",
            payload=offer,
            zone=zone,
            crop=crop,
        )
        return self.channel.initiate_handshake(message)

    # ═══════════════════════════════════════════════════════════
    # MONITORING
    # ═══════════════════════════════════════════════════════════

    def status(self) -> Dict[str, Any]:
        """Status complet du système A2A."""
        return {
            "registry": self.registry.stats(),
            "channel": self.channel.stats(),
        }
