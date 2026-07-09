import re
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db, create_user, get_user_by_email
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)

app = Flask(__name__)

# TODO: move to an environment variable before any real deployment —
# a hardcoded secret lets anyone who can read the repo forge session cookies.
app.secret_key = "dev-only-secret-key-change-before-deploy"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not name:
        return render_template("register.html", error="Name is required.")

    if not EMAIL_RE.match(email):
        return render_template("register.html", error="Please enter a valid email address.")

    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.")

    if get_user_by_email(email) is not None:
        return render_template("register.html", error="An account with this email already exists.")

    password_hash = generate_password_hash(password)

    try:
        user_id = create_user(name, email, password_hash)
    except sqlite3.IntegrityError:
        return render_template("register.html", error="An account with this email already exists.")

    session["user_id"] = user_id
    session["user_name"] = name
    return redirect(url_for("profile"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    generic_error = "Invalid email or password."

    if not email or not password:
        return render_template("login.html", error=generic_error)

    user = get_user_by_email(email)

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error=generic_error)

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


@app.route("/profile")
@login_required
def profile():
    db_user = get_user_by_id(session["user_id"])
    name_parts = db_user["name"].split()
    initials = "".join(p[0] for p in name_parts[:2]).upper()
    user = {
        "name": db_user["name"],
        "email": db_user["email"],
        "initials": initials,
        "member_since": db_user["member_since"],
    }

    stats = get_summary_stats(session["user_id"])
    summary = {
        "total_spent": f"₹{stats['total_spent']:,.2f}",
        "transaction_count": stats["transaction_count"],
        "top_category": stats["top_category"],
    }

    raw_transactions = get_recent_transactions(session["user_id"])
    transactions = [
        {
            "date": datetime.strptime(t["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": t["description"],
            "category": t["category"],
            "amount": f"₹{t['amount']:,.2f}",
        }
        for t in raw_transactions
    ]

    raw_categories = get_category_breakdown(session["user_id"])
    categories = [
        {
            "category": c["name"],
            "amount": f"₹{c['amount']:,.2f}",
            "percent": c["pct"],
        }
        for c in raw_categories
    ]

    return render_template(
        "profile.html",
        user=user, summary=summary,
        transactions=transactions, categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
