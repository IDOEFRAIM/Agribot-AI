"""
AI Tasks — Traitement asynchrone via l'Orchestrateur réel.

PRINCIPES :
  - La tâche Celery utilise le MÊME MessageResponseFlow que la route sync.
  - Les agents ne sont JAMAIS instanciés manuellement ici.
  - L'import de l'orchestrateur est LAZY (dans la fonction, pas au top).
  - En cas d'erreur, on utilise self.retry() pour un vrai backoff Celery.
"""

import logging
from typing import Dict, Any

from backend.workers.celery_app import celery_app

logger = logging.getLogger("AgriConnect.tasks.ai")


# ── Cache du singleton orchestrateur (par worker process) ──────
_orchestrator_instance = None


def _get_orchestrator():
    """Retourne un singleton de MessageResponseFlow, lazy-loaded."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        from backend.orchestrator.message_flow import MessageResponseFlow
        _orchestrator_instance = MessageResponseFlow()
        logger.info("✅ Orchestrator loaded in worker (PID %s)", __import__("os").getpid())
    return _orchestrator_instance


@celery_app.task(
    name="backend.workers.tasks.ai.generate_response",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    acks_late=True,
)
def generate_response(
    self,
    user_query: str,
    user_id: str = "anonymous",
    zone_id: str = "Centre",
    crop: str = "Inconnue",
    voice_enabled: bool = False,
    user_level: str = "debutant",
) -> Dict[str, Any]:
    """
    Traite une requête via l'orchestrateur complet
    (LangGraph : ANALYZE → route → expert(s) → TTS → PERSIST → END).

    C'est le MÊME flow que /api/v1/ask en mode synchrone,
    mais exécuté dans un worker Celery pour ne pas bloquer l'API.
    """
    try:
        logger.info("📨 Celery task: user=%s level=%s query=%.60s…", user_id, user_level, user_query)

        orchestrator = _get_orchestrator()

        # Valider user_level
        valid_levels = ("debutant", "intermediaire", "expert")
        if user_level not in valid_levels:
            user_level = "debutant"

        # Même state que api/routes.py (synchrone)
        initial_state = {
            "requete_utilisateur": user_query,
            "zone_id": zone_id,
            "user_id": user_id,
            "crop": crop,
            "user_level": user_level,
            "user_reliability_score": 1.0,
            "is_sms_mode": False,
            "flow_type": "MESSAGE",
            "execution_path": [],
            "expert_responses": [],
            "meteo_data": {},
            "market_data": {},
            "global_alerts": [],
            "audio_url": None,
        }

        result = orchestrator.run(initial_state)

        response_text = result.get("final_response", "Pas de réponse générée.")
        audio_url = result.get("audio_url")

        # TTS additionnel via Celery (si pas déjà généré par l'orchestrateur)
        if voice_enabled and not audio_url and response_text:
            try:
                from backend.workers.tasks.voice import generate_tts
                tts_result = generate_tts.apply(args=[response_text, user_id]).result
                audio_url = tts_result.get("audio_path") if tts_result else None
            except Exception as tts_err:
                logger.warning("TTS additionnel échoué: %s", tts_err)

        logger.info("✅ Celery task done: user=%s audio=%s", user_id, bool(audio_url))
        return {
            "status": "success",
            "response": response_text,
            "audio_url": audio_url,
            "trace": result.get("execution_path", []),
        }

    except Exception as exc:
        logger.error("❌ AI task failed (attempt %d/%d): %s",
                      self.request.retries + 1, self.max_retries + 1, exc,
                      exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "status": "error",
                "response": f"Erreur après {self.max_retries + 1} tentatives: {exc}",
                "audio_url": None,
                "trace": [],
            }
