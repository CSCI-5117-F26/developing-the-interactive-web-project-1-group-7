
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

schema_path = Path(__file__).resolve().parent / "schema.sql"

schema = schema_path.read_text(encoding="utf-8")

# Connect to PostgreSQL and create tables
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute(schema)

print("Database tables created successfully!")

# Verify tables
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )

        print("\nExisting database tables:")

        for row in cur.fetchall():
            print("-", row[0])
