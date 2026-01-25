import sqlite3
import json

DB_PATH = "data/agconnect_cache.db"
ZONE_ID = "Boromo"  # zone testée : Boromo
CATEGORY = "METEO_VECTOR"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT content_json, effective_date, source_url 
    FROM raw_agent_data 
    WHERE zone_id = ? AND agent_category = ?
    ORDER BY effective_date DESC 
    LIMIT 1
""", (ZONE_ID, CATEGORY))
row = cursor.fetchone()
if row:
    data = json.loads(row['content_json'])
    print("effective_date:", row['effective_date'])
    print("source_url:", row['source_url'])
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print("Aucune donnée météo trouvée pour cette zone/catégorie.")
conn.close()
