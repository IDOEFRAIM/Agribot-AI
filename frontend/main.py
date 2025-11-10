import gradio as gr
import requests

API_URL = "http://backend:5000/reply"

def reply(userQuery, chatHistory):
    if not userQuery or not str(userQuery).strip():
        return chatHistory or [], ""

    try:
        payload = {"query": userQuery, "chatHistory": chatHistory or []}
        response = requests.post(API_URL, json=payload)
        updatedHistory = response.json()

        cleanHistory = [
            msg for msg in updatedHistory.get("chatHistory", [])
            if isinstance(msg, dict) and isinstance(msg.get("content"), str) and msg["content"].strip()
        ]

        return cleanHistory, ""

    except Exception as e:
        error_msg = {"role": "assistant", "content": f"❌ Erreur de connexion à l'API : {str(e)}"}
        return (chatHistory or []) + [error_msg], ""

def createGradioInterface():
    with gr.Blocks(title="Agriconnect") as demo:
        with gr.Tab("Chat"):
            chatbot = gr.Chatbot(height=500, type="messages")
            chatInput = gr.Textbox(label="Pose ta question", placeholder="As tu une question sur l'agriculture? Pose la et on gère le reste")
            chatBtn = gr.Button("Envoyer")

            chatBtn.click(fn=reply, inputs=[chatInput, chatbot], outputs=[chatbot, chatInput])

    return demo

if __name__ == "__main__":
    demo = createGradioInterface()
    demo.launch(server_name="0.0.0.0", server_port=8080, share=True)