"""Check DB defaults for createdAt/updatedAt columns."""
from dotenv import load_dotenv
load_dotenv()
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("DATABASE_URL"))
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT column_name, column_default, is_nullable
        FROM information_schema.columns
        WHERE table_name='conversations'
          AND column_name IN ('createdAt', 'updatedAt')
    """)).fetchall()
    for r in rows:
        print(dict(r._mapping))
