import os
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()


# Columns shared by the home cards, profile tiles and view page, selected from
# `mixtapes m JOIN users u`. Constant SQL only, never user input.
MIXTAPE_SUMMARY_SQL = """
    SELECT
        m.id,
        m.title,
        m.description,
        m.created_at,
        m.creator_id,
        m.remixed_from_id,
        -- Auth0 uses the email as the name for email signups;
        -- don't show full emails publicly
        COALESCE(u.username, split_part(u.name, '@', 1)) AS creator_name,
        (
            SELECT COUNT(*) FROM mixtape_tracks mt
            WHERE mt.mixtape_id = m.id
        ) AS track_count,
        (
            SELECT COUNT(*) FROM saved_mixtapes s
            WHERE s.mixtape_id = m.id
        ) AS saved_count,
        ARRAY(
            SELECT tag FROM mixtape_tags mtag
            WHERE mtag.mixtape_id = m.id
            ORDER BY tag
        ) AS tags,
        COALESCE(
            m.cover_image_url,
            (
                SELECT t.album_image_url
                FROM mixtape_tracks mt
                JOIN tracks t ON t.spotify_id = mt.spotify_id
                WHERE mt.mixtape_id = m.id
                ORDER BY mt.position
                LIMIT 1
            )
        ) AS cover_image_url
    FROM mixtapes m
    JOIN users u ON u.auth0_id = m.creator_id
"""


# Open a new connection; `with` commits on success and rolls back on error
def get_db_connection():
    return psycopg.connect(os.environ["DATABASE_URL"])


# Create or update a user after Auth0 login
def save_user(user):
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


# Create a mixtape with its tags and ordered tracks 
def create_mixtape(user_id, title, description, tags=(), tracks=()):
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

            _insert_mixtape_tags(cur, mixtape_id, tags)
            _insert_mixtape_tracks(cur, mixtape_id, tracks)

    return mixtape_id


# Add tags to a mixtape 
def _insert_mixtape_tags(cur, mixtape_id, tags):
    cur.executemany(
        """
        INSERT INTO mixtape_tags (mixtape_id, tag)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        """,
        [(mixtape_id, tag) for tag in tags],
    )


# Cache Spotify track details, then add the tracks to the mixtape in order
def _insert_mixtape_tracks(cur, mixtape_id, tracks):
    cur.executemany(
        """
        INSERT INTO tracks
            (spotify_id, title, artist, album, duration_ms, album_image_url)
        VALUES
            (%(spotify_id)s, %(title)s, %(artist)s, %(album)s,
             %(duration_ms)s, %(album_image_url)s)
        ON CONFLICT (spotify_id) DO UPDATE SET
            title = EXCLUDED.title,
            artist = EXCLUDED.artist,
            album = EXCLUDED.album,
            duration_ms = EXCLUDED.duration_ms,
            album_image_url = EXCLUDED.album_image_url
        """,
        tracks,
    )

    cur.executemany(
        """
        INSERT INTO mixtape_tracks (mixtape_id, spotify_id, position, annotation)
        VALUES (%s, %s, %s, %s)
        """,
        [
            (mixtape_id, track["spotify_id"], position, track.get("annotation"))
            for position, track in enumerate(tracks, start=1)
        ],
    )


# Recent mixtapes for the home page, or only those with any of the tags
def list_mixtapes(tags=(), limit=48):
    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                MIXTAPE_SUMMARY_SQL + """
                WHERE
                    cardinality(%(tags)s::text[]) = 0
                    OR EXISTS (
                        SELECT 1
                        FROM mixtape_tags mtag
                        WHERE mtag.mixtape_id = m.id
                          AND mtag.tag = ANY(%(tags)s::text[])
                    )
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT %(limit)s
                """,
                {"tags": list(tags), "limit": limit},
            )

            return cur.fetchall()


# Mixtapes created by a user, newest first
def list_user_mixtapes(user_id):
    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                MIXTAPE_SUMMARY_SQL + """
                WHERE m.creator_id = %s
                ORDER BY m.created_at DESC, m.id DESC
                """,
                (user_id,),
            )

            return cur.fetchall()


# Mixtapes a user saved, most recently saved first
def list_saved_mixtapes(user_id):
    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                MIXTAPE_SUMMARY_SQL + """
                JOIN saved_mixtapes sm ON sm.mixtape_id = m.id
                WHERE sm.user_id = %s
                ORDER BY sm.saved_at DESC
                """,
                (user_id,),
            )

            return cur.fetchall()


# Mixtapes whose title or description contains the search text
def search_mixtapes(query):
    conn = get_db_connection()
    cur = conn.cursor(row_factory=dict_row)
    cur.execute(MIXTAPE_SUMMARY_SQL + " WHERE m.title ILIKE %s OR m.description ILIKE %s ORDER BY m.created_at DESC, m.id DESC", (f"%{query}%", f"%{query}%"))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# One mixtape with its ordered tracks and remix source, or None if it doesn't exist
def get_mixtape(mixtape_id):
    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(MIXTAPE_SUMMARY_SQL + " WHERE m.id = %s", (mixtape_id,))
            mixtape = cur.fetchone()

            if mixtape is None:
                return None

            cur.execute(
                """
                SELECT
                    mt.position,
                    mt.annotation,
                    t.spotify_id,
                    t.title,
                    t.artist,
                    t.album,
                    t.duration_ms,
                    t.album_image_url
                FROM mixtape_tracks mt
                JOIN tracks t ON t.spotify_id = mt.spotify_id
                WHERE mt.mixtape_id = %s
                ORDER BY mt.position
                """,
                (mixtape_id,),
            )
            mixtape["tracks"] = cur.fetchall()

            mixtape["remixed_from"] = None
            if mixtape["remixed_from_id"]:
                cur.execute(
                    MIXTAPE_SUMMARY_SQL + " WHERE m.id = %s",
                    (mixtape["remixed_from_id"],),
                )
                mixtape["remixed_from"] = cur.fetchone()

    return mixtape


# Whether the user has saved this mixtape
def is_mixtape_saved(user_id, mixtape_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM saved_mixtapes
                WHERE user_id = %s AND mixtape_id = %s
                """,
                (user_id, mixtape_id),
            )

            return cur.fetchone() is not None


# Save a mixtape for a user 
def save_mixtape(user_id, mixtape_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO saved_mixtapes (user_id, mixtape_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (user_id, mixtape_id),
            )


# Remove a mixtape from a user's saved list
def unsave_mixtape(user_id, mixtape_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM saved_mixtapes
                WHERE user_id = %s AND mixtape_id = %s
                """,
                (user_id, mixtape_id),
            )


# Delete a mixtape, only if this user created it; its tracks, tags and saves go with it
def delete_mixtape(user_id, mixtape_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM mixtapes
                WHERE id = %s AND creator_id = %s
                """,
                (mixtape_id, user_id),
            )


# Note to dev
# Run `python -m developing_the_interactive_web_project_1_group_7.db` to test the connection
if __name__ == "__main__":
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user;")
            print("Connected successfully!")
            print("Database:", cur.fetchone())
