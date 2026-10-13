import os

from flask import Flask, redirect, request, render_template
from dotenv import load_dotenv
import requests 

load_dotenv()


app = Flask(__name__)

# Added this so I could run my html easier, feel free to change anything this is just temp routing

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/login")
def login():
    return render_template("login.html")

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