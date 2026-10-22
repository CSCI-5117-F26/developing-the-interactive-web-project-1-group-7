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

def save_mixtape(user_id, mixtape_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO saved_mixtapes (user_id, mixtape_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, mixtape_id))
    conn.commit()
    cur.close()
    conn.close()

def unsave_mixtape(user_id, mixtape_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM saved_mixtapes WHERE user_id = %s AND mixtape_id = %s", (user_id, mixtape_id))
    conn.commit()
    cur.close()
    conn.close()

def get_saved_mixtapes(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT mixtapes.id, mixtapes.title, mixtapes.description, mixtapes.created_at FROM saved_mixtapes JOIN mixtapes ON mixtapes.id = saved_mixtapes.mixtape_id WHERE saved_mixtapes.user_id = %s ORDER BY saved_mixtapes.saved_at DESC", (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

if __name__ == "__main__":
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user;")
            print("Connected successfully!")
            print("Database:", cur.fetchone())