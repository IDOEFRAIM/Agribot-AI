"""
WhatsApp Tasks — Envoi de messages via Twilio (Celery).

Config lue depuis backend.core.settings (plus de os.getenv).
Twilio est importé DANS la tâche (lazy).
"""

import logging

from backend.workers.celery_app import celery_app
from backend.core.settings import settings

logger = logging.getLogger("AgriConnect.tasks.whatsapp")


@celery_app.task(
    name="backend.workers.tasks.whatsapp.send_message",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def send_message(self, to_number: str, message: str, media_url: str = None):
    """Envoie un message WhatsApp via Twilio."""
    try:
        sid = settings.TWILIO_ACCOUNT_SID
        token = settings.TWILIO_AUTH_TOKEN
        from_num = settings.TWILIO_WHATSAPP_NUMBER

        if not all([sid, token, from_num]):
            logger.warning("Twilio non configuré, WhatsApp ignoré.")
            return {"status": "skipped", "reason": "Twilio not configured"}

        from twilio.rest import Client  # lazy import

        client = Client(sid, token)
        params = {
            "from_": from_num,
            "to": f"whatsapp:{to_number}",
            "body": message,
        }
        if media_url:
            params["media_url"] = [media_url]

        twilio_msg = client.messages.create(**params)
        logger.info("WhatsApp sent: %s -> %s", twilio_msg.sid, to_number)
        return {"status": "sent", "message_sid": twilio_msg.sid, "to": to_number}

    except Exception as exc:
        logger.error("WhatsApp error (attempt %d): %s", self.request.retries + 1, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "error", "reason": str(exc)}
