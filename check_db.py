
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                id,
                creator_id,
                title,
                description,
                cover_image_url,
                remixed_from_id,
                created_at
            FROM mixtapes
            ORDER BY created_at DESC, id DESC
            LIMIT 10;
        """)

        rows = cur.fetchall()

        for row in rows:
            print(row)

        if not rows:
            print("No mixtapes found.")
