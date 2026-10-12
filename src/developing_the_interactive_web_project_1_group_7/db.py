import os
import psycopg


db_url = os.environ("DATABASE_URL")

# Template code for a database interaction
    # with psycopg.connect(db_url) as conn:
    #     with conn.cursor() as cur:
    #         cur.execute("insert sql here")