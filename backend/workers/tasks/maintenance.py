"""
Maintenance Tasks — Nettoyage fichiers audio, logs, etc. (Celery).

Le répertoire audio est lu depuis settings.AUDIO_OUTPUT_DIR
(même chemin que l'API et les tâches TTS).
"""

import logging
import time
from pathlib import Path

from backend.workers.celery_app import celery_app
from backend.core.settings import settings

logger = logging.getLogger("AgriConnect.tasks.maintenance")

MAX_RETENTION_HOURS = 24


@celery_app.task(name="backend.workers.tasks.maintenance.cleanup_old_audio")
def cleanup_old_audio():
    """Supprime les fichiers .wav de plus de 24 h."""
    try:
        audio_dir = Path(settings.AUDIO_OUTPUT_DIR).resolve()
        if not audio_dir.exists():
            return {"deleted": 0, "status": "no_directory"}

        now = time.time()
        retention_seconds = MAX_RETENTION_HOURS * 3600
        deleted = 0

        for f in audio_dir.glob("*.wav"):
            if (now - f.stat().st_mtime) > retention_seconds:
                f.unlink()
                deleted += 1

        logger.info("Audio cleanup: %d fichiers supprimés", deleted)
        return {"deleted": deleted, "retention_hours": MAX_RETENTION_HOURS, "status": "success"}

    except Exception as e:
        logger.error("Audio cleanup error: %s", e)
        raise
