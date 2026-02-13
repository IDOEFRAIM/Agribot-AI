"""
Agent Voice - Interface Vocale pour Analphabètes
Gère la réception de notes vocales WhatsApp, conversion STT,
et génération de réponses TTS.
"""

import logging
import os
from typing import Dict, Any, Optional
import asyncio

# 3. Router vers l'agent approprié
from backend.orchestrator.message_flow import MessageResponseFlow
# STT (Speech-to-Text)
import whisper  # OpenAI Whisper (local, gratuit)
# Alternative cloud : Azure Speech, Google Cloud Speech

# TTS (Text-to-Speech)
from gtts import gTTS
import azure.cognitiveservices.speech as speechsdk

# Détection de langue
from langdetect import detect, LangDetectException

logger = logging.getLogger("VoiceAgent")


class VoiceAgent:
    """
    Agent vocal : transforme audio → texte → traitement → audio.
    
    Workflow :
    1. Utilisateur envoie note vocale WhatsApp
    2. Télécharger l'audio
    3. STT (Speech-to-Text) → texte + langue détectée
    4. Router vers l'agent approprié (FormationCoach, PlantDoctor, etc.)
    5. TTS (Text-to-Speech) → audio de réponse
    6. Envoyer audio via WhatsApp
    """
    
    def __init__(self):
        # Whisper pour STT (local, rapide)
        self.whisper_model = whisper.load_model("base")  # ou "small" pour plus de précision
        
        # Azure Speech (optionnel, premium)
        self.use_azure = os.getenv("USE_AZURE_SPEECH", "false").lower() == "true"
        self.azure_key = os.getenv("AZURE_SPEECH_KEY")
        self.azure_region = os.getenv("AZURE_REGION", "westeurope")
        
        # Mapping langues
        self.LANGUAGE_MAP = {
            "fr": "Français",
            "en": "English",
            # Whisper détecte automatiquement, mais pour les dialectes locaux :
            # on utilise un fallback français si pas reconnu
        }
    
    async def process_voice_message(
        self, 
        audio_file_path: str,
        user_phone: str,
        db_client
    ) -> Dict[str, Any]:
        """
        Pipeline complet : audio → texte → traitement → audio.
        
        Args:
            audio_file_path: Chemin local vers le fichier audio téléchargé
            user_phone: Numéro WhatsApp de l'utilisateur
            db_client: Client Prisma pour accès DB
        
        Returns:
            {
                "transcript": "Texte transcrit",
                "language": "fr",
                "response_text": "Réponse textuelle",
                "response_audio_url": "https://...",
                "agent_used": "FormationCoach"
            }
        """
        logger.info(f"🎤 Traitement message vocal de {user_phone}")
        
        try:
            # 1. Speech-to-Text
            transcript, detected_lang = await self._stt(audio_file_path)
            logger.info(f"📝 Transcription ({detected_lang}): {transcript[:100]}...")
            
            # 2. Récupérer profil utilisateur
            user = await db_client.user.find_unique(
                where={"phone": user_phone},
                include={"zone": True, "crops": True}
            )
            
            if not user:
                return await self._handle_new_user(user_phone, transcript, detected_lang, db_client)
            
            
            orchestrator = MessageResponseFlow()
            
            # Construire l'état initial
            initial_state = {
                "requete_utilisateur": transcript,
                "user_id": user.id,
                "zone_id": user.zoneId,
                "crop": user.crops[0].crop_name if user.crops else "Inconnue",
                "is_sms_mode": False,
                "flow_type": "MESSAGE",
                "execution_path": [],
            }
            
            # Exécuter l'orchestrateur
            result = orchestrator.run(initial_state)
            
            response_text = result.get("final_response", "Je n'ai pas compris votre question.")
            agent_used = result.get("agent_used", "Unknown")
            
            # 4. Text-to-Speech pour la réponse
            response_audio_url = await self._tts(response_text, user.language)
            
            # 5. Sauvegarder la conversation
            await self._save_conversation(user, transcript, response_text, db_client)
            
            logger.info(f"✅ Traitement vocal terminé (Agent: {agent_used})")
            
            return {
                "transcript": transcript,
                "language": detected_lang,
                "response_text": response_text,
                "response_audio_url": response_audio_url,
                "agent_used": agent_used,
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur traitement vocal: {e}", exc_info=True)
            return {
                "error": str(e),
                "response_text": "Désolé, je n'ai pas pu traiter votre message vocal.",
            }
    
    async def _stt(self, audio_path: str) -> tuple[str, str]:
        """
        Speech-to-Text : convertit audio en texte.
        
        Returns:
            (transcript, detected_language)
        """
        if self.use_azure:
            return await self._azure_stt(audio_path)
        else:
            return await self._whisper_stt(audio_path)
    
    async def _whisper_stt(self, audio_path: str) -> tuple[str, str]:
        """
        STT avec OpenAI Whisper (local, gratuit, très précis).
        """
        # Whisper est CPU-intensif, on l'exécute dans un thread séparé
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self.whisper_model.transcribe,
            audio_path
        )
        
        transcript = result["text"].strip()
        language = result.get("language", "fr")  # Détection automatique
        
        return transcript, language
    
    async def _azure_stt(self, audio_path: str) -> tuple[str, str]:
        """
        STT avec Azure Speech (premium, meilleur pour dialectes).
        
        Avantage : Support natif du Français d'Afrique de l'Ouest
        """
        speech_config = speechsdk.SpeechConfig(
            subscription=self.azure_key,
            region=self.azure_region
        )
        
        # Auto-détection de langue
        auto_detect_source_language_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
            languages=["fr-FR", "fr-BF", "en-US"]  # Burkina Faso français
        )
        
        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            auto_detect_source_language_config=auto_detect_source_language_config,
            audio_config=audio_config
        )
        
        result = recognizer.recognize_once()
        
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            detected_lang = result.properties.get(
                speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult,
                "fr"
            )
            return result.text, detected_lang
        else:
            raise Exception(f"Erreur STT Azure : {result.reason}")
    
    async def _tts(self, text: str, language: str = "fr") -> str:
        """
        Text-to-Speech : convertit texte en audio.
        
        Returns:
            URL du fichier audio généré
        """
        if self.use_azure:
            return await self._azure_tts(text, language)
        else:
            return await self._gtts_simple(text, language)
    
    async def _gtts_simple(self, text: str, language: str) -> str:
        """
        TTS avec gTTS (gratuit, basique).
        """
        lang_map = {
            "fr": "fr",
            "moore": "fr",
            "dioula": "fr",
            "en": "en",
        }
        
        tts_lang = lang_map.get(language, "fr")
        
        # Générer l'audio
        tts = gTTS(text=text, lang=tts_lang, slow=False)
        
        filename = f"response_{asyncio.get_event_loop().time()}.mp3"
        filepath = f"/tmp/{filename}"
        
        tts.save(filepath)
        
        # Upload vers cloud storage (Azure Blob, S3, etc.)
        audio_url = await self._upload_audio(filepath)
        
        return audio_url
    
    async def _azure_tts(self, text: str, language: str) -> str:
        """
        TTS avec Azure Speech (voix neuronales premium).
        """
        speech_config = speechsdk.SpeechConfig(
            subscription=self.azure_key,
            region=self.azure_region
        )
        
        # Voix neuronales africaines
        voice_map = {
            "fr": "fr-FR-DeniseNeural",  # Voix féminine
            "en": "en-US-JennyNeural",
        }
        
        speech_config.speech_synthesis_voice_name = voice_map.get(language, "fr-FR-DeniseNeural")
        
        filename = f"/tmp/response_{asyncio.get_event_loop().time()}.mp3"
        audio_config = speechsdk.audio.AudioOutputConfig(filename=filename)
        
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )
        
        result = synthesizer.speak_text_async(text).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            audio_url = await self._upload_audio(filename)
            return audio_url
        else:
            raise Exception(f"Erreur TTS Azure : {result.reason}")
    
    async def _upload_audio(self, filepath: str) -> str:
        """
        Upload audio vers Azure Blob Storage.
        
        Configuration requise (GitHub Education) :
        - AZURE_STORAGE_ACCOUNT
        - AZURE_STORAGE_KEY
        """
        # Placeholder : à implémenter selon votre cloud
        return f"https://agribot-storage.blob.core.windows.net/voice/{os.path.basename(filepath)}"
    
    async def _handle_new_user(
        self,
        phone: str,
        first_message: str,
        language: str,
        db_client
    ) -> Dict[str, Any]:
        """
        Gère un nouvel utilisateur (onboarding vocal).
        """
        logger.info(f"🆕 Nouvel utilisateur : {phone}")
        
        # Message d'accueil
        welcome_text = (
            "Bienvenue sur AgriConnect ! "
            "Je suis votre assistant agricole vocal. "
            "Pour commencer, dites-moi dans quelle région vous cultivez. "
            "Par exemple : 'Je suis à Dedougou' ou 'Je cultive à Ouahigouya'."
        )
        
        welcome_audio = await self._tts(welcome_text, language)
        
        return {
            "transcript": first_message,
            "language": language,
            "response_text": welcome_text,
            "response_audio_url": welcome_audio,
            "agent_used": "ONBOARDING",
            "action_required": "ZONE_SELECTION",
        }
    
    async def _save_conversation(
        self,
        user,
        user_message: str,
        assistant_message: str,
        db_client
    ):
        """
        Sauvegarde la conversation dans la DB.
        """
        # Créer ou récupérer la conversation du jour
        session_id = f"{user.id}_{datetime.now().strftime('%Y%m%d')}"
        
        conversation = await db_client.conversation.upsert(
            where={
                "userId_session_id": {
                    "userId": user.id,
                    "session_id": session_id
                }
            },
            create={
                "userId": user.id,
                "platform": "WHATSAPP",
                "session_id": session_id,
            },
            update={}
        )
        
        # Ajouter les messages
        await db_client.conversation_message.create_many(
            data=[
                {
                    "conversationId": conversation.id,
                    "role": "USER",
                    "content": user_message,
                    "content_type": "voice",
                },
                {
                    "conversationId": conversation.id,
                    "role": "ASSISTANT",
                    "content": assistant_message,
                    "content_type": "voice",
                }
            ]
        )


# ============================================
# INTÉGRATION WHATSAPP (Webhook)
# ============================================

from fastapi import FastAPI, Request
from twilio.twiml.messaging_response import MessagingResponse

app = FastAPI()

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """
    Webhook pour recevoir les messages WhatsApp (Twilio).
    
    Configuration Twilio :
    1. Webhook URL : https://your-domain.com/whatsapp/webhook
    2. Method : POST
    """
    from prisma import Prisma
    
    form_data = await request.form()
    
    from_number = form_data.get("From")  # whatsapp:+22670123456
    message_body = form_data.get("Body")
    num_media = int(form_data.get("NumMedia", 0))
    
    db = Prisma()
    await db.connect()
    
    voice_agent = VoiceAgent()
    
    # Si message vocal (audio)
    if num_media > 0 and form_data.get("MediaContentType0", "").startswith("audio"):
        media_url = form_data.get("MediaUrl0")
        
        # Télécharger l'audio
        audio_path = await download_audio(media_url)
        
        # Traiter
        result = await voice_agent.process_voice_message(
            audio_file_path=audio_path,
            user_phone=from_number.replace("whatsapp:", ""),
            db_client=db
        )
        
        # Répondre avec l'audio
        response = MessagingResponse()
        message = response.message()
        message.media(result["response_audio_url"])
        
        await db.disconnect()
        return str(response)
    
    # Si message texte classique
    else:
        # Router vers l'orchestrateur normal
        # ...
        pass


async def download_audio(url: str) -> str:
    """Télécharge l'audio depuis Twilio."""
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            filename = f"/tmp/voice_{asyncio.get_event_loop().time()}.ogg"
            with open(filename, "wb") as f:
                f.write(await resp.read())
            return filename
