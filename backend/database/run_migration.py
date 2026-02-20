"""Run DB migration script safely using settings.DATABASE_URL.

Usage:
    python backend/database/run_migration.py --sql-file backend/database/patch_add_userid_conversations.sql --backup

Options:
    --sql-file   Path to SQL file to execute (default: patch_add_userid_conversations.sql)
    --backup     If provided, create a SQL dump of the `conversations` table before altering.

The script uses `backend.core.settings.settings.DATABASE_URL` when available,
otherwise falls back to environment variable `DATABASE_URL`.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from backend.core.settings import settings


def get_database_url():
    url = settings.DATABASE_URL or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in settings or environment")
    return url


def run_sql_file(db_url: str, sql_file: str) -> int:
    # Use psql if available; otherwise run via psycopg2
    try:
        subprocess.check_call(["psql", db_url, "-f", sql_file])
        return 0
    except FileNotFoundError:
        # psql not installed: fallback to psycopg2
        try:
            import psycopg2
        except Exception as e:
            print("psql not found and psycopg2 not installed:", e)
            return 2

        with open(sql_file, "r", encoding="utf-8") as f:
            sql = f.read()

        conn = None
        try:
            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            cur.close()
            return 0
        except Exception as e:
            print("Error executing SQL via psycopg2:", e)
            if conn:
                conn.rollback()
            return 3
        finally:
            if conn:
                conn.close()
    except subprocess.CalledProcessError as e:
        print("psql returned non-zero exit:", e)
        return e.returncode


def backup_table(db_url: str, table: str, out_path: str) -> int:
    # Attempt pg_dump for single table
    try:
        subprocess.check_call(["pg_dump", db_url, "-t", table, "-f", out_path])
        return 0
    except FileNotFoundError:
        print("pg_dump not available; skipping backup. Install PostgreSQL client tools to enable backup.")
        return 1
    except subprocess.CalledProcessError as e:
        print("pg_dump failed:", e)
        return e.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql-file", default="backend/database/patch_add_userid_conversations.sql")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--table", default="conversations")
    args = parser.parse_args()

    db_url = get_database_url()
    sql_file = Path(args.sql_file)
    if not sql_file.exists():
        print("SQL file not found:", sql_file)
        sys.exit(1)

    if args.backup:
        out = Path(tempfile.gettempdir()) / f"backup_{args.table}.sql"
        print(f"Creating backup of table {args.table} at {out}...")
        rc = backup_table(db_url, args.table, str(out))
        if rc != 0:
            print("Backup failed or skipped (see message). Aborting migration.")
            sys.exit(rc)
        print("Backup complete.")

    print("Running migration SQL:", sql_file)
    rc = run_sql_file(db_url, str(sql_file))
    if rc == 0:
        print("Migration executed successfully.")
    else:
        print("Migration failed with code:", rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
