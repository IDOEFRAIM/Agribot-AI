"""
Services — Services externes AgriConnect.

Structure:
- external_apis/: Integrations APIs externes (Earth Engine, Weather)
- data_collection/: Collecteurs de donnees (Weather, Documents)
- scraper/: Systeme de scraping (Production-ready)
- scheduling/: Orchestration temporelle (APScheduler)
- utils/: Utilitaires transverses (cache, etc.)
- llm_clients.py: Clients LLM (Groq/ChatGroq)
- db_handler.py: Acces base de donnees (SQLAlchemy)
- voice.py: Azure TTS/STT

Les imports lourds (scraper, external APIs) sont lazy
pour ne pas ralentir le startup de l'application.
"""

from .db_handler import AgriDatabase
from .llm_clients import get_groq_client
from .voice import VoiceEngine

__all__ = [
    "AgriDatabase",
    "get_groq_client",
    "VoiceEngine",
]
