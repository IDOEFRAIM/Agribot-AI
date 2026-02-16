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



# DEPRECATION NOTICE
raise ImportError("\n[DEPRECATION] Le module main_orchestrator.py est obsolète.\nUtilisez directement MessageResponseFlow (backend/orchestrator/message_flow.py) pour toute orchestration.\n")
