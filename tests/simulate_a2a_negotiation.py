
"""
Simulation de Négociation A2A (Marketplace <-> Grossiste)
Test de charge et de logique protocolaire (Handshake, Timeout, Fallback).
"""

import sys
import os
import asyncio
import logging
from datetime import datetime

# Ajout du path pour les imports backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.protocols.a2a import A2AChannel, A2AMessage, MessageType, HandshakeStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("A2A_Simulation")

async def run_simulation():
    channel = A2AChannel()
    
    # ACTEUR 1 : Agent Marketplace (Vendeur)
    seller_id = "agent_marketplace_bobodioulasso"
    
    # ACTEUR 2 : Agent Grossiste (Acheteur)
    buyer_id = "agent_grossiste_ouaga"
    
    # Enregistrement des handlers
    def seller_handler(msg: A2AMessage):
        logger.info(f"🧑‍🌾 [Seller] Reçu: {msg.message_type.value} | Status: {msg.handshake_status}")
        
        if msg.message_type == MessageType.HANDSHAKE:
            if msg.handshake_status == HandshakeStatus.COUNTER:
                # Le grossiste propose un prix plus bas
                offer = msg.payload.get("price")
                logger.info(f"🧑‍🌾 [Seller] Contre-offre reçue: {offer} FCFA")
                
                if offer >= 180:
                    logger.info("🧑‍🌾 [Seller] Prix acceptable. J'accepte !")
                    channel.respond_handshake(msg.reference_id, seller_id, HandshakeStatus.ACCEPTED, {"final_price": offer})
                else:
                    logger.info("🧑‍🌾 [Seller] Prix trop bas. Je refuse.")
                    channel.respond_handshake(msg.reference_id, seller_id, HandshakeStatus.REJECTED, {"reason": "Prix minimum 180 FCFA"})

    def buyer_handler(msg: A2AMessage):
        logger.info(f"🏢 [Buyer] Reçu: {msg.message_type.value} de {msg.sender_id}")
        
        if msg.message_type == MessageType.BROADCAST and msg.intent == "SELL_OFFER":
            # Opportunité détectée !
            product = msg.payload.get("product")
            price = msg.payload.get("price")
            logger.info(f"🏢 [Buyer] Offre détectée : {product} à {price} FCFA. Je tente une négo.")
            
            # Initier Handshake
            proposal = A2AMessage(
                sender_id=buyer_id,
                receiver_id=msg.sender_id, # L'agent éphémère ou le seller réel
                intent="NEGOTIATE_PRICE",
                payload={"price": 170}, # Offre basse
                zone="Bobo",
                crop="Maïs"
            )
            hs_id = channel.initiate_handshake(proposal, max_turns=3, timeout=5)
            logger.info(f"🏢 [Buyer] Handshake {hs_id} lancé.")

        elif msg.message_type == MessageType.HANDSHAKE:
             if msg.handshake_status == HandshakeStatus.ACCEPTED:
                 logger.info("🏢 [Buyer] Affaire conclue ! 🎉")
             elif msg.handshake_status == HandshakeStatus.REJECTED:
                 logger.info("🏢 [Buyer] Négociation échouée. 😢")

    channel.register_handler(seller_id, seller_handler)
    channel.register_handler(buyer_id, buyer_handler)
    
    # Abonnement du grossiste aux offres de maïs
    channel.subscribe(buyer_id, "SELL_MAÏS_BOBO")
    
    logger.info("--- DÉBUT SIMULATION ---")
    
    # 1. Le Vendeur broadcast une offre (via MarketplaceAgent logique)
    # Simulation de l'action de MarketplaceAgent.match_check_node
    offer_msg = A2AMessage(
        message_type=MessageType.BROADCAST,
        sender_id=seller_id,
        intent="SELL_OFFER",
        zone="Bobo",
        crop="Maïs",
        payload={
            "product": "Maïs",
            "quantity": 1000,
            "price": 200,
            "seller_phone": "+226..."
        }
    )
    
    # Broadcast sur le topic
    channel.broadcast(offer_msg, topic="SELL_MAÏS_BOBO")
    
    # Laisser le temps aux callbacks asynchrones (simulés ici en synchrone par l'appel direct dans send(), 
    # mais en prod ce serait via RabbitMQ/Redis)
    
    # NOTE: Dans A2AChannel.send() actuel, c'est synchrone pour la démo.
    # Donc tout s'est déjà passé lors du broadcast et des réponses en chaîne.
    
    logger.info("--- FIN SIMULATION ---")
    
    # Vérification Audit
    stats = channel.stats()
    logger.info(f"📊 Stats Canal: {stats}")

if __name__ == "__main__":
    asyncio.run(run_simulation())
