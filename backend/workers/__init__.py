"""
Workers — Celery async task infrastructure.

- celery_app   : L'app Celery unique (backend.workers.celery_app)
- tasks/ai     : Traitement IA via l'orchestrateur
- tasks/voice  : TTS / STT Azure
- tasks/whatsapp: Envoi WhatsApp via Twilio
- tasks/monitoring: Météo périodique (Celery Beat)
- tasks/maintenance: Nettoyage audio
"""
