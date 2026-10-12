from flask import Flask, redirect, request, render_template

app = Flask(__name__)

# Added this so I could run my html easier, feel free to change anything this is just temp routing

@app.route("/")
def home():
    return render_template("home.html")