from datetime import datetime

from database.db import get_db


def _date_range_filter(date_from, date_to):
    """
    Internal helper. Returns (sql_fragment, params_tuple). Only applies a
    filter when both bounds are given; a lone bound is treated as no filter.
    """
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", (date_from, date_to)
    return "", ()


def get_user_by_id(user_id):
    """
    OWNER: Subagent 2 (User + Summary).
    Returns {"name": str, "email": str, "member_since": "Month YYYY"} or
    None if the user does not exist. member_since is derived from
    users.created_at and formatted here (not in app.py).
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        created = datetime.strptime(row["created_at"].split(" ")[0], "%Y-%m-%d")
        return {
            "name": row["name"],
            "email": row["email"],
            "member_since": created.strftime("%B %Y"),
        }
    finally:
        conn.close()


def get_summary_stats(user_id, date_from=None, date_to=None):
    """
    OWNER: Subagent 2 (User + Summary).
    Returns {"total_spent": float, "transaction_count": int, "top_category": str}.
    Zero-expenses case must return
    {"total_spent": 0, "transaction_count": 0, "top_category": "—"}
    rather than raising.
    """
    conn = get_db()
    try:
        clause, date_params = _date_range_filter(date_from, date_to)
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            + "FROM expenses WHERE user_id = ?" + clause,
            (user_id, *date_params),
        ).fetchone()
        if totals["cnt"] == 0:
            return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

        top = conn.execute(
            "SELECT category, SUM(amount) AS cat_total "
            + "FROM expenses WHERE user_id = ?" + clause
            + " GROUP BY category ORDER BY cat_total DESC LIMIT 1",
            (user_id, *date_params),
        ).fetchone()

        return {
            "total_spent": totals["total"],
            "transaction_count": totals["cnt"],
            "top_category": top["category"],
        }
    finally:
        conn.close()


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """
    OWNER: Subagent 1 (Transactions).
    Returns a list of {"date": "YYYY-MM-DD", "description": str,
    "category": str, "amount": float}, most-recent-first. [] if none.
    Dates stay in raw ISO form here; app.py reformats for display.
    """
    conn = get_db()
    try:
        clause, date_params = _date_range_filter(date_from, date_to)
        rows = conn.execute(
            "SELECT date, description, category, amount "
            + "FROM expenses WHERE user_id = ?" + clause
            + " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *date_params, limit),
        ).fetchall()
        return [
            {
                "date": r["date"],
                "description": r["description"],
                "category": r["category"],
                "amount": r["amount"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """
    OWNER: Subagent 3 (Categories).
    Returns a list of {"name": str, "amount": float, "pct": int},
    sorted by amount descending. [] if no expenses. pct values are
    integers that sum to exactly 100: floor each category's raw
    percentage, then add the entire rounding remainder to the largest
    category (index 0, since rows are sorted descending).
    """
    conn = get_db()
    try:
        clause, date_params = _date_range_filter(date_from, date_to)
        rows = conn.execute(
            "SELECT category, SUM(amount) AS cat_total "
            + "FROM expenses WHERE user_id = ?" + clause
            + " GROUP BY category ORDER BY cat_total DESC",
            (user_id, *date_params),
        ).fetchall()
        if not rows:
            return []

        grand_total = sum(r["cat_total"] for r in rows)
        breakdown = [
            {
                "name": r["category"],
                "amount": r["cat_total"],
                "pct": int((r["cat_total"] / grand_total) * 100),
            }
            for r in rows
        ]
        remainder = 100 - sum(b["pct"] for b in breakdown)
        if remainder:
            breakdown[0]["pct"] += remainder  # largest category absorbs it
        return breakdown
    finally:
        conn.close()
