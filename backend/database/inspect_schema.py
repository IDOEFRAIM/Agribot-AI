"""Inspect DB schema for all shared tables."""
from backend.core.settings import settings
import psycopg2

conn = psycopg2.connect(settings.DATABASE_URL)
cur = conn.cursor()

tables = ["users", "zones", "conversations", "agent_actions", "orders", "producers", "products", "external_context_files"]

for table in tables:
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name=%s ORDER BY ordinal_position",
        (table,),
    )
    rows = cur.fetchall()
    if rows:
        print(f"\n=== {table} ({len(rows)} cols) ===")
        for r in rows:
            print(f"  {r[0]:30s} {r[1]}")
    else:
        print(f"\n=== {table} — NOT FOUND ===")

cur.close()
conn.close()
