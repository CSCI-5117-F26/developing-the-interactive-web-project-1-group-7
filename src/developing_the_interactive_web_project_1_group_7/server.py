import base64
import io
import os
import re
import time
from functools import wraps
from itertools import zip_longest
from urllib.parse import urlencode

import requests
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask import Flask, abort, redirect, request, render_template, send_file, session, url_for
from werkzeug.utils import secure_filename

from .db import (
    save_user,
    create_mixtape,
    update_mixtape,
    list_mixtapes,
    list_user_mixtapes,
    list_saved_mixtapes,
    search_mixtapes,
    get_mixtape,
    is_mixtape_saved,
    save_mixtape,
    unsave_mixtape,
    delete_mixtape,
    cover_to_db,
)

load_dotenv()


app = Flask(__name__)

# Filter tags
MIXTAPE_TAGS = ["late-night", "morning", "sleepy", "chill", "pop", "alternative", "heartbreak", "study", "driving", "workout", "party", "getting-ready"]

MAX_TRACKS = 50
MAX_ANNOTATION_LENGTH = 300
SPOTIFY_ID_PATTERN = re.compile(r"[A-Za-z0-9]{22}")
SPOTIFY_SEARCH_LIMIT = 10

app.secret_key = os.environ["FLASK_SECRET_KEY"]

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true",
)


# Auth0
oauth = OAuth(app)

oauth.register(
    name="auth0",
    client_id=os.environ["AUTH0_CLIENT_ID"],
    client_secret=os.environ["AUTH0_CLIENT_SECRET"],
    server_metadata_url=(
        f"https://{os.environ['AUTH0_DOMAIN']}"
        "/.well-known/openid-configuration"
    ),
    client_kwargs={"scope": "openid profile email"},
)


# Decorator: send logged-out visitors to the login page
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


# Login
@app.route("/login")
def login():
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("callback", _external=True)
    )


# Sign up
@app.route("/signup")
def signup():
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("callback", _external=True),
        screen_hint="signup"
    )


# Validate the Auth0 login response and save the user
@app.route("/callback")
def callback():
    token = oauth.auth0.authorize_access_token()

    user = dict(token["userinfo"])
    save_user(user)

    session.clear()
    session["user"] = user

    return redirect(url_for("home"))


# Logout
@app.route("/logout")
def logout():
    session.clear()

    params = urlencode({
        "returnTo": url_for("home", _external=True),
        "client_id": os.environ["AUTH0_CLIENT_ID"]
    })

    return redirect(
        f"https://{os.environ['AUTH0_DOMAIN']}/v2/logout?{params}"
    )


# Home page
# recent mixtapes, filtered by any selected tags
@app.route("/")
def home():
    selected_tags = [
        tag for tag in request.args.getlist("tag") if tag in MIXTAPE_TAGS
    ]

    return render_template(
        "home.html",
        mixtape_tags=MIXTAPE_TAGS,
        selected_tags=selected_tags,
        mixtapes=list_mixtapes(selected_tags)
    )


# Profile
# users own and saved mixtapes
@app.route("/profile")
@requires_auth
def profile():
    user = session["user"]

    return render_template(
        "profile.html",
        name=user.get("name", "User"),
        my_mixtapes=list_user_mixtapes(user["sub"]),
        saved_mixtapes=list_saved_mixtapes(user["sub"])
    )


# /view without an id goes home
@app.route("/view")
def view_without_id():
    return redirect(url_for("home"))


# View one mixtape and its songs
@app.route("/view/<int:mixtape_id>")
def view(mixtape_id):
    user = session.get("user")

    mixtape = get_mixtape(mixtape_id)
    if mixtape is None:
        abort(404)

    saved = bool(user) and is_mixtape_saved(user["sub"], mixtape_id)
    # check if the logged-in user is the creator of this mixtape?
    is_owner = bool(user) and user["sub"] == mixtape["creator_id"]
    return render_template(
        "view_mixtape.html",
        mixtape=mixtape,
        mixtape_id=mixtape_id,
        is_owner=is_owner,
        saved=saved
    )

@app.route("/view/<int:mixtape_id>/export")
def export(mixtape_id):
    mixtape = get_mixtape(mixtape_id)
    if mixtape is None:
        abort(404)
    lines = []
    for track in mixtape["tracks"]:
        lines.append(f"{track["position"]} {track["title"]} by {track["artist"]}")

    data = "\n".join(lines)
    
    buffer = io.BytesIO(data.encode("utf-8"))
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{mixtape["title"]}.txt",
        mimetype='text/plain'
    )


# Create a mixtape
@app.route("/create", methods=["GET", "POST"])
@requires_auth
def create():
    if request.method == "POST":
        fields, error = read_mixtape_form()
        if error:
            return error

        create_mixtape(session["user"]["sub"], **fields)

        return redirect(url_for("profile"))

    return render_mixtape_editor("create", url_for("create"))


# Edit your own mixtape in the same editor as create
@app.route("/mixtape/<int:mixtape_id>/edit", methods=["GET", "POST"])
@requires_auth
def edit(mixtape_id):
    user = session["user"]

    mixtape = get_mixtape(mixtape_id)
    if mixtape is None:
        abort(404)
    if mixtape["creator_id"] != user["sub"]:
        abort(403)

    if request.method == "POST":
        fields, error = read_mixtape_form()
        if error:
            return error

        update_mixtape(user["sub"], mixtape_id, **fields)

        return redirect(url_for("view", mixtape_id=mixtape_id))

    return render_mixtape_editor("edit", url_for("edit", mixtape_id=mixtape_id), mixtape)


# Remix: start from a copy of any mixtape (yours or someone else's) and save it as a new one of your own
@app.route("/mixtape/<int:mixtape_id>/remix", methods=["GET", "POST"])
@requires_auth
def remix(mixtape_id):
    source = get_mixtape(mixtape_id)
    if source is None:
        abort(404)

    if request.method == "POST":
        fields, error = read_mixtape_form()
        if error:
            return error

        new_id = create_mixtape(session["user"]["sub"], **fields, remixed_from_id=mixtape_id)

        return redirect(url_for("view", mixtape_id=new_id))

    return render_mixtape_editor("remix", url_for("remix", mixtape_id=mixtape_id), source)


# Show the shared mixtape editor; mode is "create", "edit" or "remix"
def render_mixtape_editor(mode, form_action, mixtape=None):
    return render_template(
        "add_mixtape.html",
        mode=mode,
        form_action=form_action,
        mixtape=mixtape,
        name=session["user"].get("name", "User"),
        mixtape_tags=MIXTAPE_TAGS
    )


# Check the editor form; returns (fields for create/update_mixtape, None) or (None, error response)
def read_mixtape_form():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()

    if not title or len(title) > 150:
        return None, ("Title must be between 1 and 150 characters.", 400)

    tags = [
        tag for tag in request.form.getlist("tags") if tag in MIXTAPE_TAGS
    ]

    # Each song row submits a track_ids and an annotations value, in order.
    # Keep the submitted order, drop duplicates.
    annotations = {}
    for track_id, note in zip_longest(
        request.form.getlist("track_ids"),
        request.form.getlist("annotations"),
        fillvalue=""
    ):
        annotations.setdefault(track_id, note.strip() or None)
    track_ids = list(annotations)

    if len(track_ids) > MAX_TRACKS:
        return None, (f"A mixtape can have at most {MAX_TRACKS} songs.", 400)

    if not all(SPOTIFY_ID_PATTERN.fullmatch(t) for t in track_ids):
        return None, ("Invalid song.", 400)

    if any(note and len(note) > MAX_ANNOTATION_LENGTH for note in annotations.values()):
        return None, (f"Song notes can be at most {MAX_ANNOTATION_LENGTH} characters.", 400)

    try:
        tracks = get_spotify_tracks(track_ids)
        for track in tracks:
            track["annotation"] = annotations[track["spotify_id"]]
    except LookupError:
        return None, ("One of the songs could not be found on Spotify.", 400)
    except (requests.RequestException, KeyError, ValueError):
        app.logger.exception("Spotify track lookup failed")
        return None, ("Spotify is unavailable right now. Please try again.", 502)

    fields = {"title": title, "description": description, "tags": tags, "tracks": tracks}
    return fields, None


# Redirecting just for compatibility - should work without this
@app.route("/add")
def add():
    return redirect(url_for("create"))


@app.route("/mixtape/<int:mixtape_id>/edit/upload_cover", methods=["POST"])
def upload_cover(mixtape_id):
    user_id = session["user"]
    file = request.files["image"]
    # maybe not needed?
    # filename = secure_filename(file.filename)
    filestream = file.read()
    cover_to_db(filestream, user_id, mixtape_id)


# Preview of the search results modal (frontend WIP)
@app.route("/search-test")
def search2():
    return render_template("search_modal.html")


# Search mixtapes by title or description (header search bar)
@app.route("/search")
def search():
    query = request.args.get("q", "").strip()

    results = []
    if query:
        results = search_mixtapes(query)

    return render_template("search_modal.html", query=query, results=results)


# Save a mixtape to the user's profile
@app.route("/mixtape/<int:mixtape_id>/save", methods=["POST"])
@requires_auth
def save(mixtape_id):
    save_mixtape(session["user"]["sub"], mixtape_id)
    app.logger.info("mixtape saved")
    return {"saved": True}


# Remove a mixtape from the user's saved list
@app.route("/mixtape/<int:mixtape_id>/unsave", methods=["POST"])
@requires_auth
def unsave(mixtape_id):
    unsave_mixtape(session["user"]["sub"], mixtape_id)
    app.logger.info("mixtape unsaved")
    return {"saved": False}


# Delete a mixtape the user created
@app.route("/mixtape/<int:mixtape_id>/delete", methods=["POST"])
@requires_auth
def delete(mixtape_id):
    delete_mixtape(session["user"]["sub"], mixtape_id)
    app.logger.info("mixtape deleted")
    return redirect(url_for("profile"))


# Search Spotify for songs (JSON, used by the create page)
@app.route("/api/tracks/search")
@requires_auth
def search_spotify_tracks():
    query = request.args.get("q", "").strip()

    if not query:
        return {"tracks": []}

    if len(query) > 100:
        return {"error": "Search query is too long."}, 400

    try:
        response = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {get_access_token()}"},
            params={
                "q": query,
                "type": "track",
                "limit": SPOTIFY_SEARCH_LIMIT
            },
            timeout=10
        )

        response.raise_for_status()
        results = response.json()

    except (requests.RequestException, KeyError, ValueError):
        app.logger.exception("Spotify search failed")
        return {"error": "Spotify search unavailable."}, 502

    tracks = [
        spotify_track_to_dict(item)
        for item in results.get("tracks", {}).get("items", [])
    ]

    return {"tracks": tracks}


# Convert a Spotify track object into the shape we store in `tracks`
def spotify_track_to_dict(item):
    album = item.get("album") or {}
    images = album.get("images") or []
    artists = item.get("artists") or []

    return {
        "spotify_id": item["id"],
        "title": item["name"],
        "artist": ", ".join(
            artist["name"] for artist in artists
        ),
        "album": album.get("name"),
        "duration_ms": item.get("duration_ms"),
        "album_image_url": (
            images[0]["url"] if images else None
        )
    }


# Look up songs on Spotify in the given order; LookupError if an id is unknown
def get_spotify_tracks(track_ids):
    if not track_ids:
        return []

    access_token = get_access_token()
    tracks = []

    for track_id in track_ids:
        response = requests.get(
            f"https://api.spotify.com/v1/tracks/{track_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )

        if response.status_code in (400, 404):
            raise LookupError(track_id)

        response.raise_for_status()
        tracks.append(spotify_track_to_dict(response.json()))

    return tracks


# Cached Spotify app token (tokens last an hour)
_spotify_token = {"value": None, "expires_at": 0}


# Get a Spotify app token, reusing the cached one until a minute before it expires
def get_access_token():
    if _spotify_token["value"] and time.time() < _spotify_token["expires_at"] - 60:
        return _spotify_token["value"]

    credentials = f"{os.environ['SPOTIFY_CLIENT_ID']}:{os.environ['SPOTIFY_CLIENT_SECRET']}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={"grant_type": "client_credentials"},
        timeout=10
    )
    response.raise_for_status()
    data = response.json()

    _spotify_token["value"] = data["access_token"]
    _spotify_token["expires_at"] = time.time() + data.get("expires_in", 3600)

    return _spotify_token["value"]


# Template filter: milliseconds to m:ss, rounded down like Spotify (213573 -> 3:33)
@app.template_filter("duration")
def format_duration(ms):
    if not ms:
        return ""
    minutes, seconds = divmod(ms // 1000, 60)
    return f"{minutes}:{seconds:02d}"


# page for unknown URLs and missing mixtapes
@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404
