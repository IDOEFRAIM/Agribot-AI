"""End-to-end INSERT test for Conversation with camelCase column mapping."""
from dotenv import load_dotenv
load_dotenv()
import os, uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.services.models import Conversation

engine = create_engine(os.getenv("DATABASE_URL"), pool_pre_ping=True)
Session = sessionmaker(bind=engine)
session = Session()

# Find a valid user
row = session.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
if not row:
    print("No users in DB — skipping"); exit()

uid = row[0]
cid = "test-" + str(uuid.uuid4())[:8]
print(f"Using user_id={uid}, conv_id={cid}")

conv = Conversation(
    id=cid,
    user_id=uid,
    query="Test question depuis SQLAlchemy",
    response="Réponse alignée Prisma camelCase",
    agent_type="formation",
    mode="text",
)
session.add(conv)
session.commit()
print("✅ INSERT successful!")

# Read back via raw SQL to verify camelCase columns
result = session.execute(text(
    """SELECT id, "userId", query, response, "agentType", mode, "createdAt", "updatedAt"
       FROM conversations WHERE id = :cid"""
), {"cid": cid}).fetchone()
print(f"Read back: {dict(result._mapping)}")

# Clean up
session.execute(text("DELETE FROM conversations WHERE id = :cid"), {"cid": cid})
session.commit()
print("✅ Cleanup done")
session.close()
