from flask import Flask, redirect, request, render_template

app = Flask(__name__)

# Added this so I could run my html easier, feel free to change anything this is just temp routing

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/edit")
def edit():
    return render_template("edit_mixtape.html")

@app.route("/create")
def create():
    return render_template("mixtape_template.html")

@app.route("/view")
def view():
    return render_template("view_mixtape.html")