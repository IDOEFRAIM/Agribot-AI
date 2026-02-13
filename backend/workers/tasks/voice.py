"""
Voice Tasks — TTS / STT via Azure Speech (Celery).

PRINCIPES :
  - azure.cognitiveservices.speech est importé DANS la tâche (lazy).
    → Un worker sans le SDK Azure n'explosera pas au démarrage.
  - Toute la config vient de backend.core.settings (plus de os.getenv).
  - Le répertoire audio est settings.AUDIO_OUTPUT_DIR (cohérent avec l'API).
  - self.retry() est utilisé pour un vrai backoff Celery.
"""

import logging
import uuid
from pathlib import Path

from backend.workers.celery_app import celery_app
from backend.core.settings import settings

logger = logging.getLogger("AgriConnect.tasks.voice")

AUDIO_DIR = Path(settings.AUDIO_OUTPUT_DIR).resolve()


@celery_app.task(
    name="backend.workers.tasks.voice.generate_tts",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def generate_tts(self, text: str, user_id: str = "unknown"):
    """
    Génère un fichier audio .wav via Azure TTS.

    Returns:
        dict: {"audio_id", "audio_path", "status"}
    """
    try:
        key = settings.AZURE_SPEECH_KEY or settings.AZURE_SPEECH_KEY_2
        if not key:
            logger.warning("Azure Speech non configuré, TTS ignoré.")
            return {"status": "skipped", "reason": "No Azure key"}

        # Import LAZY — pas au top du module
        import azure.cognitiveservices.speech as speechsdk

        audio_id = str(uuid.uuid4())
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        audio_path = AUDIO_DIR / f"{audio_id}.wav"

        speech_config = speechsdk.SpeechConfig(
            subscription=key,
            region=settings.AZURE_REGION,
        )
        speech_config.speech_synthesis_voice_name = "fr-FR-DeniseNeural"

        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(audio_path))
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.info("🔊 TTS OK: %s (%d chars)", audio_id, len(text))
            return {"audio_id": audio_id, "audio_path": str(audio_path), "status": "success"}

        raise RuntimeError(f"TTS failed: {result.reason}")

    except Exception as exc:
        logger.error("TTS error (attempt %d/%d): %s",
                      self.request.retries + 1, self.max_retries + 1, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "error", "reason": str(exc)}


@celery_app.task(
    name="backend.workers.tasks.voice.transcribe_audio",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def transcribe_audio(self, audio_file_path: str):
    """
    Transcrit un fichier audio en texte via Azure STT.

    Returns:
        dict: {"text", "status"}
    """
    try:
        key = settings.AZURE_SPEECH_KEY or settings.AZURE_SPEECH_KEY_2
        if not key:
            return {"text": "", "status": "skipped"}

        import azure.cognitiveservices.speech as speechsdk

        speech_config = speechsdk.SpeechConfig(subscription=key, region=settings.AZURE_REGION)
        speech_config.speech_recognition_language = "fr-FR"

        audio_config = speechsdk.audio.AudioConfig(filename=audio_file_path)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        result = recognizer.recognize_once_async().get()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return {"text": result.text, "status": "success"}
        return {"text": "", "status": "no_match"}

    except Exception as exc:
        logger.error("STT error: %s", exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"text": "", "status": "error", "reason": str(exc)}
