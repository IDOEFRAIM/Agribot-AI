import sqlite3
import json

DB_PATH = "data/agconnect_cache.db"
CATEGORY = "METEO_VECTOR"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT zone_id FROM raw_agent_data WHERE agent_category = ?
""", (CATEGORY,))
rows = cursor.fetchall()
if rows:
    print("Zones météo présentes dans la base :")
    for row in rows:
        print("-", row["zone_id"])
else:
    print("Aucune zone météo trouvée.")
conn.close()
