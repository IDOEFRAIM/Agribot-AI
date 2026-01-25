import os
from groq import Groq
from dotenv import load_dotenv
from langchain_groq import ChatGroq
# Charger la clé API depuis le fichier .env
load_dotenv()
api_key = os.getenv("AGRICONNECT_APIKEY")

# Initialiser le client Groq
# groq_client.py


# Au lieu de : client = Groq(api_key=...)
client = ChatGroq(
    api_key=api_key,
    model_name="llama-3.1-8b-instant", # ou ton modèle habituel
    temperature=0
)
#client = Groq(api_key=api_key)

# Exporter le client pour réutilisation
__all__ = ["client"]
