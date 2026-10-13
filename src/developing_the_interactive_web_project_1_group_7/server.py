import os

from flask import Flask, redirect, request, render_template, session, url_for
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import requests 
from .db import save_user, create_mixtape, get_user_mixtapes

load_dotenv()


app = Flask(__name__)
#Auth0
app.secret_key = os.environ["FLASK_SECRET_KEY"]

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true",
)

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

# Login
@app.route("/login")
def login():
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("callback", _external=True)
    )

# validate authentication response
@app.route("/callback")
def callback():
    token = oauth.auth0.authorize_access_token()

    user = dict(token["userinfo"])

    # Save or update the user in PostgreSQL
    save_user(user)

    session.clear()
    session["user"] = user

    return redirect(url_for("home"))

# SignUp
@app.route("/signup")
def signup():
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("callback", _external=True),
        screen_hint="signup"
    )

# Logout
@app.route("/logout")
def logout():
    session.clear()

    return_to = url_for("home", _external=True)

    from urllib.parse import urlencode

    params = urlencode({
        "returnTo": return_to,
        "client_id": os.environ["AUTH0_CLIENT_ID"]
    })

    return redirect(
        f"https://{os.environ['AUTH0_DOMAIN']}/v2/logout?{params}"
    )
# Testing the session - temp code
@app.route("/profile")
def profile():
    user = session.get("user")

    if not user:
        return redirect(url_for("login"))

    return f"""
        <h2>Welcome, {user.get('name', 'User')}!</h2>
        <p>You are successfully logged in</p>
        <a href="/logout">Logout</a>
    """
# @app.route("/profile")
# def profile():
#     return render_template("profile.html")

# Added this so I could run my html easier, feel free to change anything this is just temp routing

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/create")
def create():
    # temporary for now 
    return redirect("/create/search")

# I don't know if this would work, it's pieced together from multiple sources
@app.route("/create/search", methods=["GET", "POST"])
def track_search():
    if request.method=="POST":
        access_token = get_access_token()
        headers={"Authorization": f"Bearer {access_token}"}
        query = request.get.form["q"]
        response = request.get(f"https://api.spotify.com/v1/search?q={query}&type=track", headers=headers)
        return response.json()
    return render_template("create.html")

# Attempt to convert the javascript to python (leaving the javascript in case)
def get_access_token():
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
    authOptions = {
        "url": 'https://accounts.spotify.com/api/token',
        "headers": {
            'Authorization': f"Basic {client_id} : {client_secret}"
        },
        "form": {
            "grant_type": 'client_credentials'
        }
    }
    response = request.post(authOptions)
    return response

@app.route("/edit")
def edit():
    return render_template("edit_mixtape.html")

# @app.route("/create")
# def create():
#     return render_template("mixtape_template.html")

@app.route("/view")
def view():
    return render_template("view_mixtape.html")

@app.route("/guest")
def guest():
    return render_template("guest_base.html")

@app.route("/remix")
def remix():
    return render_template("remix_mixtape.html")

@app.route("/my-mixtape")
def my_mixtape():
    return render_template("my_mixtape.html")
# @app.route("/guest")
# def guest():
#     return render_template("guest_base.html")

# Temp create mixtape to test db
@app.route("/demo/create", methods=["GET", "POST"])
def demo_create():
    user = session.get("user")

    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        if not title or len(title) > 150:
            return "Title must be between 1 and 150 characters.", 400

        mixtape_id = create_mixtape(
            user["sub"],
            title,
            description
        )

        return redirect(url_for("demo_create"))

    mixtapes = get_user_mixtapes(user["sub"])

    return render_template(
        "demo_create.html",
        mixtapes=mixtapes
    )
