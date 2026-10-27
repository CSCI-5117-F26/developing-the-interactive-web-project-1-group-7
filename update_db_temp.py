
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

with psycopg.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE images (
                            user_id TEXT NOT NULL
                                REFERENCES users(auth0_id),
                            mixtape_id BIGINT NOT NULL
                                REFERENCES mixtapes(id) on DELETE CASCADE,
                            stream BYTEA NOT NULL,
                            
                            PRIMARY KEY (mixtape_id)
                        );
                
        """)

print("images updated successfully!")
