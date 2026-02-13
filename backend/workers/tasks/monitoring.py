"""
Monitoring Tasks — Tâches périodiques planifiées par Celery Beat.

check_weather_alerts : interroge ClimateSentinel pour les zones surveillées
                       et PERSISTE les alertes critiques en DB.
"""

import logging
from datetime import datetime, timezone

from backend.workers.celery_app import celery_app

logger = logging.getLogger("AgriConnect.tasks.monitoring")

# Zones par défaut à surveiller (extensible via DB plus tard)
MONITORED_ZONES = [
    {"village": "Bobo-Dioulasso", "zone": "Hauts-Bassins", "country": "Burkina Faso"},
    {"village": "Ouagadougou",   "zone": "Centre",        "country": "Burkina Faso"},
]


def _get_db():
    """Lazy-load de la couche DB pour le worker Celery."""
    from backend.services.db_handler import AgriDatabase
    from backend.core.settings import settings
    if not settings.DATABASE_URL:
        return None
    return AgriDatabase(db_url=settings.DATABASE_URL)


@celery_app.task(
    name="backend.workers.tasks.monitoring.check_weather_alerts",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def check_weather_alerts(self):
    """
    Tâche périodique (6 h) : interroge ClimateSentinel pour chaque zone,
    collecte et PERSISTE les alertes critiques en base de données.
    """
    try:
        # Lazy import — le worker ne charge l'agent que quand il en a besoin
        from backend.agents.sentinelle import ClimateSentinel
        from backend.rag.components import get_groq_sdk

        llm = get_groq_sdk()
        agent = ClimateSentinel(llm_client=llm)
        workflow = agent.build()
        db = _get_db()

        all_alerts = []
        persisted = 0

        for loc in MONITORED_ZONES:
            try:
                result = workflow.invoke({
                    "user_query": f"Alertes météo pour {loc['village']}",
                    "location_profile": loc,
                })
                hazards = result.get("hazards", [])
                critical = [h for h in hazards if h.get("severity") in ("HAUT", "CRITIQUE")]

                if critical:
                    all_alerts.extend(critical)
                    logger.warning("%d alertes pour %s", len(critical), loc["village"])

                    # ── PERSISTANCE EN DB ──────────────────────────────
                    if db:
                        for h in critical:
                            try:
                                db.create_alert(
                                    alert_type=h.get("type", "WEATHER"),
                                    severity=h.get("severity", "HAUT"),
                                    message=h.get("description", f"Alerte météo {loc['village']}"),
                                    zone_id=loc.get("zone", "unknown"),
                                )
                                persisted += 1
                            except Exception as db_err:
                                logger.error("DB persist alert error: %s", db_err)
            except Exception as zone_err:
                logger.error("Monitoring %s échoué: %s", loc["village"], zone_err)

        logger.info(
            "Monitoring terminé — %d alertes critiques, %d persistées en DB",
            len(all_alerts), persisted,
        )
        return {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alerts_found": len(all_alerts),
            "alerts_persisted": persisted,
            "alerts": all_alerts,
        }

    except Exception as exc:
        logger.error("Weather monitoring error: %s", exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "error", "reason": str(exc)}
