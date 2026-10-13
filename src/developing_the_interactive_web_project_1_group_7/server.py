import os

from flask import Flask, redirect, request, render_template

app = Flask(__name__)

# Added this so I could run my html easier, feel free to change anything this is just temp routing

@app.route("/")
def home():
    return render_template("home.html")


# I don't know if this would work, it's pieced together from multiple sources
@app.route("/create/search")
def track_search():
    access_token = get_access_token()
    headers={"Authorization": f"Bearer {access_token}"}
    query = request.get.args["q"]
    response = request.get(f"https://api.spotify.com/v1/search?q={query}&type=track", headers=headers)
    return response.json()

# Attempt to convert the javascript to python (leaving the javascript in case)
def get_access_token():
    client_id = os.environ("SPOTIFY_CLIENT_ID")
    client_secret = os.environ("SPOTIFY_CLIENT_SECRET")
    authOptions = {
        "url": 'https://accounts.spotify.com/api/token',
        "headers": {
            'Authorization': f"Basic {client_id} : {client_secret}"
        },
        "form": {
            "grant_type": 'client_credentials'
        },
        "json": True
    }
    response = request.post(authOptions)
    return response

