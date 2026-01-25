import sqlite3
import json
import os
import hashlib
from datetime import datetime

# Chemins
DB_PATH = "data/agconnect_cache.db"
WEATHER_JSON = "data/weather_service_latest.json"

# Charger les données météo JSON
with open(WEATHER_JSON, encoding="utf-8") as f:
    weather_data = json.load(f)

# Pour chaque ville, insérer dans la base
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

for entry in weather_data.get("results", []):
    city = entry.get("metadata", {}).get("city", "unknown")
    content_json = json.dumps(entry, ensure_ascii=False)
    effective_date = datetime.now().isoformat()
    source_url = entry.get("url", "")
    # Calcul du hash pour éviter les doublons
    data_hash = hashlib.md5(content_json.encode('utf-8')).hexdigest()
    # Insertion (remplace si déjà présent pour la ville)
    c.execute("""
        INSERT OR REPLACE INTO raw_agent_data (zone_id, agent_category, content_json, effective_date, source_url, data_hash)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (city, "METEO_VECTOR", content_json, effective_date, source_url, data_hash))

conn.commit()
conn.close()
print("✅ Données météo insérées dans le cache pour les agents.")
