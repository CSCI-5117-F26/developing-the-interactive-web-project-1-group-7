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

from .db import (
    get_or_create_account,
    get_user,
    is_username_available,
    set_username,
    delete_account,
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
    get_cover,
)

load_dotenv()


app = Flask(__name__)

# Filter tags
MIXTAPE_TAGS = ["late-night", "morning", "sleepy", "chill", "pop", "alternative", "heartbreak", "study", "driving", "workout", "party", "getting-ready"]

MAX_TRACKS = 50
MAX_DESCRIPTION_LENGTH = 500
MAX_ANNOTATION_LENGTH = 110
SPOTIFY_ID_PATTERN = re.compile(r"[A-Za-z0-9]{22}")
SPOTIFY_SEARCH_LIMIT = 10
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,20}")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# Pages a logged-in user can reach before picking a username
USERNAME_NOT_NEEDED = {"choose_username", "username_available", "logout", "login", "signup", "callback", "static"}

app.secret_key = os.environ["FLASK_SECRET_KEY"]

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
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


# Before every request: drop logins saved in the old session format, and send users without a username to pick one
@app.before_request
def check_session():
    user = session.get("user")
    if user is None:
        return

    # Sessions from before account linking stored Auth0's login id, not our account id
    if "id" not in user:
        session.clear()
        return

    if not user.get("username") and request.endpoint not in USERNAME_NOT_NEEDED:
        return redirect(url_for("choose_username"))


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


# Validate the Auth0 login response and log in to the matching Mixtape account
@app.route("/callback")
def callback():
    if request.args.get("error"):
        return redirect(url_for("home"))
    try:
        token = oauth.auth0.authorize_access_token()
    except Exception:
        app.logger.exception("Login callback failed")
        return redirect(url_for("login"))
    userinfo = dict(token["userinfo"])

    session.clear()

    # Email/password accounts must click the verification link before they can log in
    if not userinfo.get("email_verified"):
        return render_template("verify_email.html", email=userinfo.get("email")), 403

    account = get_or_create_account(userinfo)

    # Only our own account id and username are kept in the session
    session["user"] = {"id": account["id"], "username": account["username"]}

    if not account["username"]:
        return redirect(url_for("choose_username"))

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
        username=user["username"],
        my_mixtapes=list_user_mixtapes(user["id"]),
        saved_mixtapes=list_saved_mixtapes(user["id"])
    )


# Pick a username after the first login (required before using the site)
@app.route("/welcome/username", methods=["GET", "POST"])
@requires_auth
def choose_username():
    user = session["user"]
    if user.get("username"):
        return redirect(url_for("home"))

    if request.method == "POST":
        error = save_username(user["id"], request.form.get("username", ""))
        if error:
            return render_template("username.html", mode="choose", username=request.form.get("username", ""), error=error), 400

        return redirect(url_for("home"))

    account = get_user(user["id"])
    return render_template("username.html", mode="choose", username=suggest_username(account["name"] if account else ""))


# Edit profile: change your username
@app.route("/profile/edit", methods=["GET", "POST"])
@requires_auth
def edit_profile():
    user = session["user"]

    if request.method == "POST":
        error = save_username(user["id"], request.form.get("username", ""))
        if error:
            return render_template("username.html", mode="edit", username=request.form.get("username", ""), current_username=user["username"], error=error), 400

        return redirect(url_for("profile"))

    return render_template("username.html", mode="edit", username=user["username"], current_username=user["username"])


# Delete your account and everything in it, then log out
@app.route("/profile/delete", methods=["POST"])
@requires_auth
def delete_my_account():
    delete_account(session["user"]["id"])
    app.logger.info("account deleted")
    return redirect(url_for("logout"))


# Live check while typing on the username page: is it the right format, and is it free?
@app.route("/api/username-available")
@requires_auth
def username_available():
    username = request.args.get("username", "").strip()
    valid = bool(USERNAME_PATTERN.fullmatch(username))
    available = valid and is_username_available(username, session["user"]["id"])
    return {"valid": valid, "available": available}


# Check and save a username; returns an error message, or None if it was saved
def save_username(user_id, username):
    username = username.strip()

    if not USERNAME_PATTERN.fullmatch(username):
        return "Usernames are 3-20 characters: letters, numbers and _ only."

    if not set_username(user_id, username):
        return f'"{username}" is already taken. Try another one.'

    session["user"] = {**session["user"], "username": username}
    return None


# Suggest a free username from the person's name, e.g. "Poojitha Chandu" -> "poojitha_chandu"
def suggest_username(name):
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").split("@")[0].lower()).strip("_")[:16]
    if len(base) < 3:
        base = "mixtaper"

    candidate = base
    number = 2
    while not is_username_available(candidate) and number < 100:
        candidate = f"{base}{number}"
        number += 1

    return candidate


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

    saved = bool(user) and is_mixtape_saved(user["id"], mixtape_id)
    # check if the logged-in user is the creator of this mixtape?
    is_owner = bool(user) and user["id"] == mixtape["creator_id"]
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

        file = request.files.get("image")
        if file is None or file.filename == "":
            file = None
        if file and not allowed_file(file.filename):
            return COVER_TYPE_ERROR, 400

        new_id = create_mixtape(session["user"]["id"], **fields)
        if file:
            cover_to_db(file.read(), session["user"]["id"], new_id)

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
    if mixtape["creator_id"] != user["id"]:
        abort(403)

    if request.method == "POST":
        fields, error = read_mixtape_form()
        if error:
            return error

        file = request.files.get("image")
        if file is None or file.filename == "":
            file = None
        if file and not allowed_file(file.filename):
            return COVER_TYPE_ERROR, 400

        update_mixtape(user["id"], mixtape_id, **fields)
        if file:
            cover_to_db(file.read(), user["id"], mixtape_id)

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

        file = request.files.get("image")
        if file is None or file.filename == "":
            file = None
        if file and not allowed_file(file.filename):
            return COVER_TYPE_ERROR, 400

        new_id = create_mixtape(session["user"]["id"], **fields, remixed_from_id=mixtape_id)
        if file:
            cover_to_db(file.read(), session["user"]["id"], new_id)

        return redirect(url_for("view", mixtape_id=new_id))

    return render_mixtape_editor("remix", url_for("remix", mixtape_id=mixtape_id), source)


# Show the shared mixtape editor; mode is "create", "edit" or "remix"
def render_mixtape_editor(mode, form_action, mixtape=None):
    return render_template(
        "add_mixtape.html",
        mode=mode,
        form_action=form_action,
        mixtape=mixtape,
        name=session["user"]["username"],
        mixtape_tags=MIXTAPE_TAGS
    )


# Check the editor form; returns (fields for create/update_mixtape, None) or (None, error response)
def read_mixtape_form():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()

    if not title or len(title) > 150:
        return None, ("Title must be between 1 and 150 characters.", 400)

    if len(description) > MAX_DESCRIPTION_LENGTH:
        return None, (f"Description can be at most {MAX_DESCRIPTION_LENGTH} characters.", 400)

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


COVER_TYPE_ERROR = "Cover must be a PNG, JPG, GIF or WebP image."

# Only image files
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Send a mixtape's uploaded cover image to the browser
@app.route("/mixtape/<int:mixtape_id>/cover")
def cover_image(mixtape_id):
    image = get_cover(mixtape_id)
    if image is None:
        abort(404)
    return send_file(io.BytesIO(image), mimetype="image/png")


# Search mixtapes
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
    if get_mixtape(mixtape_id) is None:
        return {"error": "This mixtape no longer exists."}, 404
    save_mixtape(session["user"]["id"], mixtape_id)
    app.logger.info("mixtape saved")
    return {"saved": True}


# Remove a mixtape from the user's saved list
@app.route("/mixtape/<int:mixtape_id>/unsave", methods=["POST"])
@requires_auth
def unsave(mixtape_id):
    unsave_mixtape(session["user"]["id"], mixtape_id)
    app.logger.info("mixtape unsaved")
    return {"saved": False}


# Delete a mixtape the user created
@app.route("/mixtape/<int:mixtape_id>/delete", methods=["POST"])
@requires_auth
def delete(mixtape_id):
    delete_mixtape(session["user"]["id"], mixtape_id)
    app.logger.info("mixtape deleted")
    return redirect(url_for("profile"))


# Search Spotify for songs (JSON, used by the create page)
@app.route("/api/tracks/search")
@requires_auth
def search_spotify_tracks():
    query = request.args.get("q", "").strip()

    if not query or len(query) == 0:
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
