"""
Drop the duplicate snake_case `user_id` column from conversations table.
Prisma already has `userId` (camelCase) — our earlier migration accidentally added a second `user_id`.
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text, inspect

DB_URL = os.getenv("DATABASE_URL", "")
if not DB_URL:
    print("❌ DATABASE_URL not set"); sys.exit(1)

engine = create_engine(DB_URL)
inspector = inspect(engine)

# Check if BOTH userId and user_id exist
cols = {c["name"] for c in inspector.get_columns("conversations")}
print(f"Columns in conversations: {sorted(cols)}")

if "user_id" in cols and "userId" in cols:
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE conversations DROP COLUMN IF EXISTS "user_id"'))
    print("✅ Dropped duplicate 'user_id' column (keeping Prisma's 'userId')")
elif "user_id" in cols and "userId" not in cols:
    print("⚠️  Only user_id exists (no userId). NOT dropping — would lose data.")
else:
    print("✅ No duplicate — only 'userId' exists. Nothing to do.")

# Verify final state
cols_after = {c["name"] for c in inspect(engine).get_columns("conversations")}
print(f"Final columns: {sorted(cols_after)}")
