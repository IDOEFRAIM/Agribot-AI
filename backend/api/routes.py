"""
Routes API — Endpoints de l'API AgriConnect.

L'orchestrateur est initialisé une seule fois (lazy singleton)
et injecté via FastAPI Depends().
"""

import asyncio
import logging
import re
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse

from backend.core.database import check_connection
from backend.orchestrator.message_flow import MessageResponseFlow
from backend.workers.tasks.ai import generate_response
from backend.core.settings import settings
from backend.orchestrator.state import GlobalAgriState
from .schemas import UserRequest, SuccessResponse, AsyncQueuedResponse, TaskStatusResponse

logger = logging.getLogger("AgriConnect.API")

router = APIRouter()


# ── Dependency : Orchestrator (lazy singleton, thread-safe) ──

_orchestrator_instance = None
_orchestrator_lock = threading.Lock()


def _get_orchestrator():
    """Instancié une seule fois, au premier appel — thread-safe, retryable."""
    global _orchestrator_instance
    if _orchestrator_instance is not None:
        return _orchestrator_instance

    with _orchestrator_lock:
        # Double-check after acquiring lock
        if _orchestrator_instance is not None:
            return _orchestrator_instance
        
        try:
            _orchestrator_instance = MessageResponseFlow()
            logger.info("Orchestrator loaded successfully.")
            return _orchestrator_instance
        except Exception as e:
            logger.warning("Failed to load Orchestrator: %s", e, exc_info=True)
            # Do NOT cache None — next call will retry
            return None


def get_orchestrator():
    """FastAPI dependency — retourne le singleton ou lève 503."""
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable. Retrying on next request.")
    return orch


# ── Routes ──────────────────────────────────────────────────

@router.post("/api/v1/ask", response_model=None)
async def ask_agent(
    req: UserRequest,
    background_tasks: BackgroundTasks,
    orchestrator=Depends(get_orchestrator),
):
    """
    Endpoint principal — interagit avec l'Orchestrateur AgConnect.

    - async_mode=False : Traitement synchrone (réponse immédiate)
    - async_mode=True  : Queue vers Celery (TTS, tasks longues)
    """
    logger.info("Request received: user=%s zone=%s async=%s", req.user_id, req.zone_id, req.async_mode)

    # --- Mode asynchrone (Celery) ---
    if req.async_mode:
        try:
            # Valider user_level avant dispatch
            valid_levels = ("debutant", "intermediaire", "expert")
            user_level = req.user_level if req.user_level in valid_levels else "debutant"

            task = generate_response.delay(
                user_query=req.query,
                user_id=req.user_id,
                zone_id=req.zone_id,
                crop=req.crop,
                voice_enabled=True,
                user_level=user_level,
            )
            return AsyncQueuedResponse(
                task_id=task.id,
                check_status_at=f"/api/v1/task/{task.id}",
            )
        except Exception as e:
            logger.warning("Async queueing failed, falling back to sync: %s", e)

    # --- Mode synchrone (non-blocking: run in thread pool) ---
    # Valider le user_level
    valid_levels = ("debutant", "intermediaire", "expert")
    user_level = req.user_level if req.user_level in valid_levels else "debutant"

    initial_state: GlobalAgriState = {
        "requete_utilisateur": req.query,
        "zone_id": req.zone_id,
        "user_id": req.user_id,
        "crop": req.crop,
        "user_reliability_score": 1.0,
        "is_sms_mode": False,
        "flow_type": req.flow_type,
        "user_level": user_level,
        "execution_path": [],
        "expert_responses": [],
        "meteo_data": {},
        "market_data": {},
        "global_alerts": [],
        "audio_url": None,
    }

    try:
        # Run blocking orchestrator in a thread pool to avoid blocking the event loop
        result = await asyncio.to_thread(orchestrator.run, initial_state)
        final_text = result.get("final_response", "Je n'ai pas pu générer de réponse.")
        audio_url = result.get("audio_url")
        audio_download = None
        if audio_url:
            audio_id = Path(audio_url).stem
            audio_download = f"/api/v1/audio/{audio_id}"

        logger.info("Response generated (audio=%s)", "yes" if audio_url else "no")
        return SuccessResponse(
            response=final_text,
            audio_url=audio_download,
            trace=result.get("execution_path", []),
        )
    except Exception as e:
        logger.warning("Orchestrator execution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Processing failed. Please try again.")


@router.get("/api/v1/task/{task_id}")
async def get_task_status(task_id: str):
    """Vérifier le statut d'une tache Celery async."""
    try:
        from backend.workers.celery_app import celery_app
        task_result = celery_app.AsyncResult(task_id)
        if task_result.ready():
            if task_result.successful():
                return {"status": "completed", "result": task_result.result}
            return {"status": "failed", "error": "Task execution failed."}
        return {"status": "processing", "task_id": task_id}
    except Exception as e:
        logger.warning("Task status error: %s", e)
        raise HTTPException(status_code=503, detail="Task broker unavailable")


# ── Audio download ──────────────────────────────────────────

AUDIO_DIR = Path(settings.AUDIO_OUTPUT_DIR).resolve()
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Regex: UUID only (hex + dashes), prevents path traversal
_AUDIO_ID_PATTERN = re.compile(r"^[a-fA-F0-9\-]{1,64}$")


@router.get("/api/v1/audio/{audio_id}")
async def download_audio(audio_id: str):
    """Telecharger un fichier audio genere par le TTS."""
    # Validate audio_id format (UUID only — no slashes, dots, etc.)
    if not _AUDIO_ID_PATTERN.match(audio_id):
        raise HTTPException(status_code=400, detail="Invalid audio ID format")

    file_path = (AUDIO_DIR / f"{audio_id}.wav").resolve()

    # Ensure resolved path is still within AUDIO_DIR (path traversal protection)
    if not str(file_path).startswith(str(AUDIO_DIR)):
        raise HTTPException(status_code=400, detail="Invalid audio ID")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path=str(file_path), media_type="audio/wav", filename=f"{audio_id}.wav")


# ── Health / Root ───────────────────────────────────────────

@router.get("/health")
def health_check():
    """Health check avec etat DB."""
    
    db_ok = check_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "version": settings.APP_VERSION,
    }


@router.get("/")
def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }
