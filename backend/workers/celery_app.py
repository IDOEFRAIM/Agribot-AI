"""
Celery App — Configuration centralisée des tâches asynchrones.

C'est le SEUL point de définition de l'app Celery.
Ne PAS redéfinir celery_app ailleurs (ex: worker.py).
"""

from celery import Celery
from celery.schedules import crontab

from backend.core.settings import settings

# ===== CELERY APP =====
celery_app = Celery(
    "agriconnect",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
)

# ===== CONFIGURATION =====
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Africa/Ouagadougou",
    enable_utc=True,
    
    # Task routing par queue
    task_routes={
        "backend.workers.tasks.voice.*": {"queue": "voice"},
        "backend.workers.tasks.ai.*": {"queue": "ai"},
        "backend.workers.tasks.whatsapp.*": {"queue": "whatsapp"},
        "backend.workers.tasks.monitoring.*": {"queue": "monitoring"},
    },
    
    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=300,  # 5 minutes max
    task_soft_time_limit=240,
    
    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    
    # Result backend
    result_expires=3600,  # 1 heure
)

# ===== PERIODIC TASKS (Celery Beat) =====
celery_app.conf.beat_schedule = {
    # Monitoring météo toutes les 6h
    "weather-monitoring": {
        "task": "backend.workers.tasks.monitoring.check_weather_alerts",
        "schedule": crontab(hour="*/6", minute=0),
    },
    
    # Nettoyage audio quotidien (3h)
    "cleanup-audio": {
        "task": "backend.workers.tasks.maintenance.cleanup_old_audio",
        "schedule": crontab(hour=3, minute=0),
    },
}

# ===== AUTO-DISCOVER TASKS =====
celery_app.autodiscover_tasks([
    "backend.workers.tasks",
])


if __name__ == "__main__":
    celery_app.start()
