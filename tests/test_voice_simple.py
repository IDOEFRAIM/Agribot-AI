"""
Test simple de l'interface vocale Azure Speech
Sans Gradio - Test direct en ligne de commande
"""

import os
from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk
from gtts import gTTS
import tempfile

# Charger .env
load_dotenv()

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_REGION = os.getenv("AZURE_REGION", "westeurope")
USE_AZURE_SPEECH = os.getenv("USE_AZURE_SPEECH", "false").lower() == "true"

def test_azure_tts(text: str = "Bonjour, je suis Agri-OS, votre assistant agricole intelligent."):
    """
    Test de synthèse vocale Azure
    """
    print("\n" + "="*60)
    print("🧪 TEST AZURE TEXT-TO-SPEECH (TTS)")
    print("="*60)
    
    if not AZURE_SPEECH_KEY or not USE_AZURE_SPEECH:
        print("❌ Azure Speech non configuré")
        print(f"   AZURE_SPEECH_KEY: {AZURE_SPEECH_KEY[:20] if AZURE_SPEECH_KEY else 'Non défini'}...")
        print(f"   USE_AZURE_SPEECH: {USE_AZURE_SPEECH}")
        return None
    
    try:
        speech_config = speechsdk.SpeechConfig(
            subscription=AZURE_SPEECH_KEY,
            region=AZURE_REGION
        )
        
        # Voix féminine française neurale (haute qualité)
        speech_config.speech_synthesis_voice_name = "fr-FR-DeniseNeural"
        
        # Créer fichier temporaire
        output_file = "test_azure_tts_output.wav"
        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
        
        speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )
        
        print(f"\n📝 Texte à synthétiser: \"{text}\"")
        print(f"🎤 Voix: fr-FR-DeniseNeural")
        print(f"🌍 Région: {AZURE_REGION}")
        print("\n⏳ Génération de l'audio...")
        
        result = speech_synthesizer.speak_text_async(text).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print(f"\n✅ Synthèse vocale réussie !")
            print(f"📁 Fichier audio créé: {output_file}")
            print(f"🔊 Vous pouvez l'écouter avec: Start-Process {output_file}")
            return output_file
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print(f"\n❌ Synthèse annulée:")
            print(f"   Raison: {cancellation.reason}")
            print(f"   Détails: {cancellation.error_details}")
            return None
        
    except Exception as e:
        print(f"\n❌ Erreur Azure TTS: {e}")
        return None


def test_azure_stt(audio_file: str = "test_audio.wav"):
    """
    Test de reconnaissance vocale Azure
    """
    print("\n" + "="*60)
    print("🧪 TEST AZURE SPEECH-TO-TEXT (STT)")
    print("="*60)
    
    if not os.path.exists(audio_file):
        print(f"❌ Fichier audio introuvable: {audio_file}")
        print("💡 Conseil: Créez d'abord un audio avec test_azure_tts()")
        return None
    
    if not AZURE_SPEECH_KEY or not USE_AZURE_SPEECH:
        print("❌ Azure Speech non configuré")
        return None
    
    try:
        speech_config = speechsdk.SpeechConfig(
            subscription=AZURE_SPEECH_KEY,
            region=AZURE_REGION
        )
        speech_config.speech_recognition_language = "fr-FR"
        
        audio_config = speechsdk.audio.AudioConfig(filename=audio_file)
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config
        )
        
        print(f"\n📁 Fichier audio: {audio_file}")
        print(f"🌍 Langue: fr-FR")
        print(f"🌍 Région: {AZURE_REGION}")
        print("\n⏳ Transcription en cours...")
        
        result = speech_recognizer.recognize_once()
        
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            print(f"\n✅ Transcription réussie !")
            print(f"📝 Texte reconnu: \"{result.text}\"")
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            print("\n❌ Aucune parole détectée dans l'audio")
            return None
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print(f"\n❌ Reconnaissance annulée:")
            print(f"   Raison: {cancellation.reason}")
            print(f"   Détails: {cancellation.error_details}")
            return None
        
    except Exception as e:
        print(f"\n❌ Erreur Azure STT: {e}")
        return None


def test_gtts_fallback(text: str = "Ceci est un test avec gTTS gratuit."):
    """
    Test de synthèse vocale gTTS (fallback gratuit)
    """
    print("\n" + "="*60)
    print("🧪 TEST gTTS (FALLBACK GRATUIT)")
    print("="*60)
    
    try:
        output_file = "test_gtts_output.mp3"
        print(f"\n📝 Texte: \"{text}\"")
        print(f"🎤 Moteur: Google TTS (gTTS)")
        print("\n⏳ Génération audio...")
        
        tts = gTTS(text=text, lang="fr", slow=False)
        tts.save(output_file)
        
        print(f"\n✅ Audio gTTS créé !")
        print(f"📁 Fichier: {output_file}")
        print(f"🔊 Écouter avec: Start-Process {output_file}")
        return output_file
        
    except Exception as e:
        print(f"\n❌ Erreur gTTS: {e}")
        return None


def show_config():
    """
    Affiche la configuration actuelle
    """
    print("\n" + "="*60)
    print("⚙️  CONFIGURATION AZURE SPEECH")
    print("="*60)
    
    print(f"\n✅ AZURE_SPEECH_KEY: {AZURE_SPEECH_KEY[:20] if AZURE_SPEECH_KEY else '❌ Non défini'}...")
    print(f"✅ AZURE_REGION: {AZURE_REGION}")
    print(f"✅ USE_AZURE_SPEECH: {USE_AZURE_SPEECH}")
    print(f"\n📦 Modules:")
    print(f"   - azure-cognitiveservices-speech: ✅ Installé")
    print(f"   - gtts: ✅ Installé")
    print(f"   - dotenv: ✅ Installé")


if __name__ == "__main__":
    print("\n🚀 AGRI-OS - TEST INTERFACE VOCALE")
    print("="*60)
    
    # Afficher configuration
    show_config()
    
    # Menu interactif
    print("\n📋 TESTS DISPONIBLES:")
    print("   1. Test Azure TTS (Synthèse vocale)")
    print("   2. Test Azure STT (Reconnaissance vocale)")
    print("   3. Test gTTS (Fallback gratuit)")
    print("   4. Test complet (TTS → STT → TTS)")
    print("   5. Quitter")
    
    while True:
        choice = input("\n👉 Votre choix (1-5): ").strip()
        
        if choice == "1":
            text = input("\n📝 Texte à synthétiser (ou Entrée pour texte par défaut): ").strip()
            if not text:
                text = "Bonjour, je suis Agri-OS. Comment puis-je vous aider aujourd'hui ?"
            test_azure_tts(text)
            
        elif choice == "2":
            audio_file = input("\n📁 Fichier audio (ou Entrée pour 'test_azure_tts_output.wav'): ").strip()
            if not audio_file:
                audio_file = "test_azure_tts_output.wav"
            test_azure_stt(audio_file)
            
        elif choice == "3":
            text = input("\n📝 Texte pour gTTS: ").strip()
            if not text:
                text = "Test de synthèse vocale avec gTTS gratuit."
            test_gtts_fallback(text)
            
        elif choice == "4":
            print("\n🔄 TEST COMPLET : TTS → STT → TTS")
            print("="*60)
            
            # Étape 1 : Créer audio
            original_text = "Quel est le meilleur moment pour planter le maïs à Bobo-Dioulasso ?"
            print(f"\n📝 Texte original: \"{original_text}\"")
            audio_file = test_azure_tts(original_text)
            
            if audio_file:
                # Étape 2 : Transcrire
                transcribed_text = test_azure_stt(audio_file)
                
                if transcribed_text:
                    # Étape 3 : Créer réponse
                    response_text = f"Vous avez demandé: {transcribed_text}. La réponse serait ici."
                    test_azure_tts(response_text)
            
        elif choice == "5":
            print("\n👋 Au revoir !")
            break
        
        else:
            print("❌ Choix invalide. Essayez encore.")
    
    print("\n✅ Tests terminés. Consultez les fichiers audio générés.")
    print("="*60)
