
import os
import sys
import psycopg
from dotenv import load_dotenv

load_dotenv()

# Read-only look at the database. Nothing is changed.
# Usage:
#   python check_db.py              tables + columns, uploaded covers, last 5 mixtapes
#   python check_db.py schema       only tables, columns, keys, indexes, row counts
#   python check_db.py images       only uploaded cover images
#   python check_db.py mixtapes 10  only the last 10 mixtapes with tags and songs
mode = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isdigit() else "all"
numbers = [arg for arg in sys.argv[1:] if arg.isdigit()]
limit = int(numbers[0]) if numbers else 5


# Every table: columns (type, required, default), primary key, links to other tables, indexes, row count
def show_schema(cur):
    print("=" * 70)
    print("TABLES AND COLUMNS")

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cur.fetchall()]

    for table in tables:
        cur.execute(f'SELECT COUNT(*) FROM "{table}";')
        print("-" * 70)
        print(f"{table}  ({cur.fetchone()[0]} rows)")

        cur.execute("""
            SELECT
                c.column_name,
                c.data_type,
                c.character_maximum_length,
                c.is_nullable,
                c.column_default,
                c.is_identity
            FROM information_schema.columns c
            WHERE c.table_schema = 'public' AND c.table_name = %s
            ORDER BY c.ordinal_position;
        """, (table,))

        for name, data_type, max_length, nullable, default, identity in cur.fetchall():
            type_text = f"{data_type}({max_length})" if max_length else data_type
            notes = []
            if nullable == "NO":
                notes.append("required")
            if identity == "YES":
                notes.append("auto id")
            elif default:
                notes.append(f"default {default}")
            elif nullable == "NO":
                notes.append("NO DEFAULT: must be given on insert")
            print(f"    {name:<18} {type_text:<26} {', '.join(notes)}")

        cur.execute("""
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = %s::regclass AND contype IN ('p', 'f', 'u', 'c')
            ORDER BY contype, conname;
        """, (f'public."{table}"',))
        for name, definition in cur.fetchall():
            print(f"    key: {definition}")

        cur.execute("""
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = %s
              AND indexname NOT IN (
                  SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass
              )
            ORDER BY indexname;
        """, (table, f'public."{table}"'))
        for name, definition in cur.fetchall():
            print(f"    index: {definition.split(' USING ', 1)[-1]}  ({name})")


# Uploaded cover images: which mixtape, who uploaded, and file size (not the image bytes)
def show_images(cur):
    print("=" * 70)
    print("UPLOADED COVER IMAGES")

    cur.execute("""
        SELECT
            i.mixtape_id,
            m.title,
            COALESCE(u.username, split_part(u.name, '@', 1), i.user_id),
            octet_length(i.stream)
        FROM images i
        LEFT JOIN mixtapes m ON m.id = i.mixtape_id
        LEFT JOIN users u ON u.auth0_id = i.user_id
        ORDER BY i.mixtape_id;
    """)
    images = cur.fetchall()

    if not images:
        print("  (no cover images uploaded)")

    for mixtape_id, title, uploader, size in images:
        size_text = f"{size / 1024:.1f} KB" if size else "EMPTY"
        print(f"  mixtape #{mixtape_id} {title or '(deleted)'} | by {uploader} | {size_text}")

    cur.execute("SELECT COUNT(*) FROM mixtapes WHERE cover_image_url IS NOT NULL;")
    print(f"  mixtapes with cover_image_url set: {cur.fetchone()[0]}")


# The most recent mixtapes with their tags and songs
def show_mixtapes(cur):
    cur.execute("""
        SELECT
            m.id,
            m.title,
            m.description,
            COALESCE(u.username, split_part(u.name, '@', 1), m.creator_id),
            m.remixed_from_id,
            m.created_at
        FROM mixtapes m
        LEFT JOIN users u ON u.auth0_id = m.creator_id
        ORDER BY m.created_at DESC, m.id DESC
        LIMIT %s;
    """, (limit,))

    mixtapes = cur.fetchall()

    print("=" * 70)
    print(f"LAST {limit} MIXTAPES")
    if not mixtapes:
        print("No mixtapes found.")

    for mixtape_id, title, description, creator, remixed_from_id, created_at in mixtapes:
        print("-" * 70)
        print(f"#{mixtape_id}  {title}")
        print(f"  by {creator}  |  created {created_at:%Y-%m-%d %H:%M}")
        if description:
            print(f"  description: {description}")
        if remixed_from_id:
            print(f"  remixed from mixtape #{remixed_from_id}")

        cur.execute("""
            SELECT tag
            FROM mixtape_tags
            WHERE mixtape_id = %s
            ORDER BY tag;
        """, (mixtape_id,))
        tags = [row[0] for row in cur.fetchall()]
        print(f"  tags: {', '.join(tags) if tags else '(none)'}")

        cur.execute("""
            SELECT
                mt.position,
                t.title,
                t.artist,
                t.duration_ms,
                mt.annotation
            FROM mixtape_tracks mt
            JOIN tracks t ON t.spotify_id = mt.spotify_id
            WHERE mt.mixtape_id = %s
            ORDER BY mt.position;
        """, (mixtape_id,))
        tracks = cur.fetchall()

        print(f"  tracks ({len(tracks)}):")
        if not tracks:
            print("    (none)")

        for position, track_title, artist, duration_ms, annotation in tracks:
            duration = ""
            if duration_ms:
                minutes, seconds = divmod(duration_ms // 1000, 60)
                duration = f" [{minutes}:{seconds:02d}]"

            print(f"    {position}. {track_title} - {artist}{duration}")
            if annotation:
                print(f"       note: {annotation}")


with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        if mode in ("all", "schema"):
            show_schema(cur)
        if mode in ("all", "images"):
            show_images(cur)
        if mode in ("all", "mixtapes"):
            show_mixtapes(cur)
        print("=" * 70)
