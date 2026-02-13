"""
Worker — Point d'entrée Celery (rétro-compatible).

USAGE:
    celery -A backend.worker:celery_app worker --loglevel=info

L'app Celery et les tâches sont définies dans backend/workers/.
Ce fichier ne fait que réexporter pour compatibilité.
"""

from backend.workers.celery_app import celery_app  # noqa: F401

__all__ = ["celery_app"]
