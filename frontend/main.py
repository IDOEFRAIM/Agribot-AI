import gradio as gr
import requests
import os
from pathlib import Path

# --- CONFIGURATION DES CHEMINS ---
# Path(__file__) est frontend/main.py
# .parent est frontend/
# .parent.parent est la racine du projet Agribot-AI/
BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "audio_output"

# S'assurer que le dossier audio existe pour éviter des erreurs au lancement
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "http://127.0.0.1:8000/api/v1/ask"

def query_backend(user_query, user_id, zone_id, crop, mode, user_level):
    """Envoie la requête au backend FastAPI et retourne la réponse."""
    flow_type = "REPORT" if mode == "Daily Report" else "MESSAGE"

    payload = {
        "user_id": user_id or "user_gradio",
        "zone_id": zone_id or "boromo",
        "crop": crop or "Inconnue",
        "query": user_query or "Generate Report",
        "flow_type": flow_type,
        "user_level": user_level or "debutant",
    }

    try:
        # Timeout de 60s car la génération audio/IA peut être longue
        response = requests.post(API_URL, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        # Récupération de la trace
        trace = data.get("trace", [])
        trace_str = " → ".join(trace) if isinstance(trace, list) else str(trace)

        # --- GESTION DE L'AUDIO ---
        audio_url_raw = data.get("audio_url")
        full_audio_path = None

        if audio_url_raw:
            # On ne garde que le nom du fichier (ex: 'output.wav') 
            # pour éviter les conflits de chemins absolus entre backend et frontend
            file_name = os.path.basename(audio_url_raw)
            temp_path = AUDIO_DIR / file_name
            
            if temp_path.exists():
                full_audio_path = str(temp_path)
            else:
                print(f"⚠️ Fichier audio introuvable physiquement : {temp_path}")

        return data.get("response", "No Content"), trace_str, full_audio_path

    except requests.exceptions.ConnectionError:
        return "❌ Backend non accessible. Vérifiez qu'il tourne sur le port 8000.", "", None
    except Exception as e:
        return f"❌ Erreur: {e}", "", None


# ── INTERFACE GRADIO ─────────────────────────────────────────
with gr.Blocks(title="AgConnect - Assistant Agricole") as demo:
    gr.Markdown("# 🌾 AgConnect — Assistant Agricole IA")

    with gr.Row():
        with gr.Column(scale=1):
            user_id = gr.Textbox(label="User ID", value="farmer_001")
            zone_id = gr.Dropdown(
                choices=["Centre", "Nord", "Sud", "Bobo-Dioulasso"],
                value="Bobo-Dioulasso", label="Zone",
            )
            crop = gr.Dropdown(
                choices=["Maïs", "Coton", "Sésame", "Sorgho", "Riz"],
                value="Maïs", label="Culture",
            )
            mode = gr.Radio(
                choices=["Conversation", "Daily Report"],
                value="Conversation", label="Mode",
            )
            user_level = gr.Dropdown(
                choices=[
                    ("Débutant (réponse rapide)", "debutant"),
                    ("Intermédiaire", "intermediaire"),
                    ("Expert / Agronome", "expert"),
                ],
                value="debutant",
                label="🎓 Niveau",
                info="Adapte la précision et le détail de la réponse",
            )

        with gr.Column(scale=2):
            output_msg = gr.Markdown(label="Réponse")
            # Utilisation de type="filepath" pour que Gradio lise le fichier sur le disque
            audio_player = gr.Audio(label="Réponse Audio", type="filepath")

    with gr.Row():
        query = gr.Textbox(label="Votre question", lines=2, placeholder="Ex: Quel temps fait-il à Bobo ?")
        submit_btn = gr.Button("🚀 Envoyer", variant="primary")

    with gr.Accordion("🛠️ Trace d'exécution", open=False):
        trace_output = gr.Textbox(label="Chemin d'exécution")

    # Liaison du bouton à la fonction
    submit_btn.click(
        fn=query_backend,
        inputs=[query, user_id, zone_id, crop, mode, user_level],
        outputs=[output_msg, trace_output, audio_player],
        show_progress="full",
    )

if __name__ == "__main__":
    # Lancement avec les autorisations de chemin
    # allowed_paths permet à Gradio d'accéder au dossier audio_output en dehors de /frontend
    demo.launch(
        server_name="127.0.0.1", 
        server_port=7860,
        allowed_paths=[str(AUDIO_DIR)]
    )