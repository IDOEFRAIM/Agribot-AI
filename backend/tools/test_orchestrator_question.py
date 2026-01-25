import requests
import json

# Adresse de l'API orchestrateur (adapter si besoin)
API_URL = "http://127.0.0.1:8000/api/v1/ask"  # Correction de l'URL pour FastAPI

# Question à poser
payload = {
    "requete_utilisateur": "Que me conseilles-tu aujourd'hui ?",
    "zone_id": "Bobo Dioulasso",
    "user_id": "test_user",
    "crop": "Maïs"
}

headers = {"Content-Type": "application/json"}

try:
    response = requests.post(API_URL, data=json.dumps(payload), headers=headers, timeout=30)
    print("Status:", response.status_code)
    print("Réponse:")
    print(response.text)
except Exception as e:
    print("Erreur lors de la requête:", e)
