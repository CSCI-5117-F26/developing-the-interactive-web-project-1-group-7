
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# Template: change the query based on requirement
with psycopg.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("""
        ALTER TABLE images (          
                ...
        """)

print("Table updated successfully!")
