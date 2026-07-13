import calendar
import math
import re
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import (
    get_db, init_db, seed_db, create_user, get_user_by_email, create_expense,
    get_expense_by_id, update_expense, delete_expense as db_delete_expense, CATEGORIES,
)
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
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _subtract_months(d, months):
    """
    Same day-of-month `months` earlier than `d`, clamped to the shorter
    month's last day when `d.day` doesn't exist there (e.g. Mar 31 minus
    1 month -> Feb 28/29, not an overflow into March).
    """
    total = d.month - 1 - months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _resolve_date_filter(args):
    """
    Reads date_from/date_to from the given query args and returns them as
    ISO strings, or (None, None) if absent, malformed, or reversed. A
    reversed range (date_from > date_to) also flashes a user-facing error.
    """
    parsed_from = _parse_iso_date(args.get("date_from"))
    parsed_to = _parse_iso_date(args.get("date_to"))

    if parsed_from and parsed_to:
        if parsed_from > parsed_to:
            flash("Start date must be before end date.", "error")
        else:
            return parsed_from.isoformat(), parsed_to.isoformat()

    return None, None


def _build_presets(today):
    """Quick-select date ranges shown on the profile filter bar."""
    last_day = calendar.monthrange(today.year, today.month)[1]
    month_start = today.replace(day=1)
    month_end = today.replace(day=last_day)
    return [
        {
            "label": "This Month",
            "date_from": month_start.isoformat(),
            "date_to": month_end.isoformat(),
        },
        {
            "label": "Last 3 Months",
            "date_from": _subtract_months(today, 3).isoformat(),
            "date_to": today.isoformat(),
        },
        {
            "label": "Last 6 Months",
            "date_from": _subtract_months(today, 6).isoformat(),
            "date_to": today.isoformat(),
        },
        {
            "label": "All Time",
            "date_from": None,
            "date_to": None,
        },
    ]

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

    if not PASSWORD_RE.match(password):
        return render_template(
            "register.html",
            error="Password must be at least 8 characters and include an uppercase letter, "
            "a lowercase letter, a number, and a special character.",
        )

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


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


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

    date_from_str, date_to_str = _resolve_date_filter(request.args)

    stats = get_summary_stats(session["user_id"], date_from_str, date_to_str)
    summary = {
        "total_spent": f"₹{stats['total_spent']:,.2f}",
        "transaction_count": stats["transaction_count"],
        "top_category": stats["top_category"],
    }

    raw_transactions = get_recent_transactions(
        session["user_id"], date_from=date_from_str, date_to=date_to_str
    )
    transactions = [
        {
            "id": t["id"],
            "date": datetime.strptime(t["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": t["description"],
            "category": t["category"],
            "amount": f"₹{t['amount']:,.2f}",
        }
        for t in raw_transactions
    ]

    raw_categories = get_category_breakdown(
        session["user_id"], date_from=date_from_str, date_to=date_to_str
    )
    categories = [
        {
            "category": c["name"],
            "amount": f"₹{c['amount']:,.2f}",
            "percent": c["pct"],
        }
        for c in raw_categories
    ]

    presets = _build_presets(date.today())
    for preset in presets:
        preset["active"] = (
            preset["date_from"] == date_from_str and preset["date_to"] == date_to_str
        )

    return render_template(
        "profile.html",
        user=user, summary=summary,
        transactions=transactions, categories=categories,
        presets=presets,
        active_date_from=date_from_str, active_date_to=date_to_str,
    )


def _render_add_expense_form(error=None):
    return render_template(
        "add_expense.html",
        categories=CATEGORIES,
        today=date.today().isoformat(),
        error=error,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "GET":
        return _render_add_expense_form()

    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()[:500]

    try:
        amount = float(amount_raw)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError
    except ValueError:
        return _render_add_expense_form(error="Please enter a valid amount greater than zero.")

    if category not in CATEGORIES:
        return _render_add_expense_form(error="Please select a valid category.")

    try:
        datetime.strptime(date_raw, "%Y-%m-%d")
    except ValueError:
        return _render_add_expense_form(error="Please enter a valid date.")

    create_expense(session["user_id"], amount, category, date_raw, description)
    return redirect(url_for("profile"))


def _render_edit_expense_form(expense_id, values, error=None):
    return render_template(
        "edit_expense.html",
        expense_id=expense_id,
        expense=values,
        categories=CATEGORIES,
        error=error,
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    expense = get_expense_by_id(id)
    if expense is None or expense["user_id"] != session["user_id"]:
        abort(404)

    if request.method == "GET":
        values = {
            "amount": expense["amount"],
            "category": expense["category"],
            "date": expense["date"],
            "description": expense["description"] or "",
        }
        return _render_edit_expense_form(id, values)

    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()[:500]

    submitted_values = {
        "amount": amount_raw,
        "category": category,
        "date": date_raw,
        "description": description,
    }

    try:
        amount = float(amount_raw)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError
    except ValueError:
        return _render_edit_expense_form(
            id, submitted_values,
            error="Please enter a valid amount greater than zero.",
        )

    if category not in CATEGORIES:
        return _render_edit_expense_form(
            id, submitted_values,
            error="Please select a valid category.",
        )

    try:
        datetime.strptime(date_raw, "%Y-%m-%d")
    except ValueError:
        return _render_edit_expense_form(
            id, submitted_values,
            error="Please enter a valid date.",
        )

    update_expense(id, amount, category, date_raw, description)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
@login_required
def delete_expense(id):
    expense = get_expense_by_id(id)
    if expense is None or expense["user_id"] != session["user_id"]:
        abort(404)

    db_delete_expense(id, session["user_id"])
    flash("Expense deleted.", "success")
    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
