import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return psycopg.connect(os.environ["DATABASE_URL"])

def save_user(user):
    """Create or update a user after Auth0 login."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (auth0_id, name, email)
                VALUES (%s, %s, %s)
                ON CONFLICT (auth0_id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    email = EXCLUDED.email
                """,
                (
                    user["sub"],
                    user.get("name"),
                    user.get("email"),
                ),
            )


def create_mixtape(user_id, title, description):
    """Create a mixtape belonging to the logged-in user."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mixtapes (creator_id, title, description)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (user_id, title, description),
            )

            mixtape_id = cur.fetchone()[0]

    return mixtape_id


def get_user_mixtapes(user_id):
    """Retrieve all mixtapes created by a user."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, description, created_at
                FROM mixtapes
                WHERE creator_id = %s
                ORDER BY created_at DESC, id DESC
                """,
                (user_id,),
            )

            return cur.fetchall()

if __name__ == "__main__":
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user;")
            print("Connected successfully!")
            print("Database:", cur.fetchone())