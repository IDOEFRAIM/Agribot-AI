import os
from groq import Groq
from dotenv import load_dotenv

# Charger la clé API depuis le fichier .env
load_dotenv()
api_key = os.getenv("AGRICONNECT_APIKEY")

# Initialiser le client
client = Groq(api_key=api_key)

def demander_conseil_expert(question):
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile", 
        messages=[
            {
                "role": "system", 
                "content": "Tu es un agronome expert au Burkina Faso. Tu aides les paysans à améliorer leur rendement."
            },
            {
                "role": "user", 
                "content": question
            }
        ],
        temperature=0.7,
        max_tokens=500
    )
    return completion.choices[0].message.content

# Test
print("Expert AgriConnect : ", demander_conseil_expert("Quand dois-je semer mon maïs si la pluie commence tardivement ?"))