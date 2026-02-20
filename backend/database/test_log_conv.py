"""Test the full db_handler.log_conversation flow."""
from dotenv import load_dotenv
load_dotenv()
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.services.db_handler import AgriDatabase

db_url = os.getenv("DATABASE_URL")
db = AgriDatabase(db_url=db_url)

# Get a valid user
engine = create_engine(db_url)
with engine.connect() as conn:
    row = conn.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
    uid = row[0] if row else "anonymous"

print(f"Testing log_conversation with user_id={uid}")
conv_id = db.log_conversation(
    user_id=uid,
    user_message="Quels sont les engrais bio pour le maïs ?",
    assistant_message="Voici les recommandations pour le maïs bio...",
    audio_url=None,
    channel="text",
)
print(f"✅ log_conversation returned conv_id={conv_id}")

# Verify in DB
with engine.connect() as conn:
    row = conn.execute(text(
        """SELECT id, "userId", query, response, mode, "createdAt", "updatedAt"
           FROM conversations WHERE id = :cid"""
    ), {"cid": conv_id}).fetchone()
    print(f"DB row: {dict(row._mapping)}")

    msgs = conn.execute(text(
        "SELECT role, content FROM conversation_messages WHERE conversation_id = :cid ORDER BY created_at"
    ), {"cid": conv_id}).fetchall()
    for m in msgs:
        print(f"  Message [{m[0]}]: {m[1][:60]}...")

    # Cleanup
    conn.execute(text("DELETE FROM conversation_messages WHERE conversation_id = :cid"), {"cid": conv_id})
    conn.execute(text("DELETE FROM conversations WHERE id = :cid"), {"cid": conv_id})
    conn.commit()
    print("✅ Cleanup done")
