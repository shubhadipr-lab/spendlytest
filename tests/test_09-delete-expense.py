"""
Tests for the "Delete Expense" feature (Step 9).

Spec covered — see .claude/specs/09-delete-expense.md (written from the spec's
"Routes", "Rules for implementation", and "Definition of done" sections, not
by reading app.py/database/db.py's implementation):

- `POST /expenses/<id>/delete` is guarded by the same `login_required`
  pattern as `/profile`, `/expenses/add`, and `/expenses/<id>/edit`: a
  logged-out request redirects (302) to `/login`, and the row must be left
  untouched.
- No `GET` handler exists for this path — a bare `GET` must not delete
  anything (405, method not allowed).
- If the expense id does not exist, or exists but belongs to a different
  user, the view must `abort(404)` — never redirect, never leak whether the
  id belongs to someone else — and the row must be left untouched.
- `POST` for an owned, existing expense deletes the row and redirects (302)
  to `/profile`.
- After deletion, the expense must no longer appear in /profile's recent
  transactions, and the summary stats and category breakdown must reflect
  its removal.
- Deleting one expense must not affect any other expense row, whether it
  belongs to the same user or a different user.
- Each row in /profile's recent-transactions table has a working delete
  control (a POST form) targeting the correct expense.

These tests reuse the `client`, `temp_db`, `demo_user`, and `empty_user`
fixtures defined in tests/conftest.py, plus a small `create_expense_for`
helper built on `database.db.create_expense` (the same DB helper the spec
says the feature is built on) to seed rows without going through the UI.
"""

from contextlib import contextmanager

import pytest
from flask import template_rendered

from app import app as flask_app
import database.db as db


# --------------------------------------------------------------------- #
# Helpers                                                                #
# --------------------------------------------------------------------- #

def login(client, user_id):
    """Fake a logged-in session the same way other tests in this suite do."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def create_expense_for(user_id, amount=50.0, category="Food",
                        expense_date="2024-01-15", description="Groceries"):
    """Seed a single expense row for `user_id` and return its id."""
    return db.create_expense(user_id, amount, category, expense_date, description)


@contextmanager
def captured_templates(app):
    """Record the names of templates rendered during the `with` block."""
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append(template.name)

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)


def count_expenses_for(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS cnt FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]
    finally:
        conn.close()


# --------------------------------------------------------------------- #
# Auth guard                                                             #
# --------------------------------------------------------------------- #

class TestDeleteExpenseAuthGuard:
    def test_post_delete_requires_login_redirects_to_login(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        response = client.post(f"/expenses/{expense_id}/delete")
        assert response.status_code == 302, "Logged-out POST must redirect, not delete"
        assert "/login" in response.headers["Location"], "Must redirect to /login"

        # The DB must be untouched by an unauthenticated attempt.
        expense = db.get_expense_by_id(expense_id)
        assert expense is not None, "Expense must still exist after an unauthenticated delete attempt"
        assert expense["amount"] == 50.0
        assert expense["category"] == "Food"


# --------------------------------------------------------------------- #
# 404 — nonexistent id / other user's expense                           #
# --------------------------------------------------------------------- #

class TestDeleteExpenseNotFound:
    def test_post_delete_nonexistent_id_returns_404(self, client, empty_user):
        login(client, empty_user)
        response = client.post("/expenses/999999/delete")
        assert response.status_code == 404

    def test_post_delete_other_users_expense_returns_404_not_redirect(
        self, client, demo_user, empty_user
    ):
        conn = db.get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? LIMIT 1", (demo_user["id"],)
        ).fetchone()
        conn.close()
        assert row is not None, "Expected the seeded demo user to have at least one expense"
        other_expense_id = row["id"]

        login(client, empty_user)
        response = client.post(f"/expenses/{other_expense_id}/delete")
        assert response.status_code == 404, (
            "Must be a 404, never a redirect, so existence of another user's id isn't leaked"
        )

    def test_post_delete_other_users_expense_does_not_delete_row(
        self, client, demo_user, empty_user
    ):
        conn = db.get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? LIMIT 1", (demo_user["id"],)
        ).fetchone()
        conn.close()
        other_expense_id = row["id"]
        original_amount = row["amount"]
        original_category = row["category"]

        login(client, empty_user)
        response = client.post(f"/expenses/{other_expense_id}/delete")
        assert response.status_code == 404

        untouched = db.get_expense_by_id(other_expense_id)
        assert untouched is not None, "Another user's expense must not be deleted"
        assert untouched["amount"] == original_amount
        assert untouched["category"] == original_category


# --------------------------------------------------------------------- #
# Method guard — GET must never delete                                  #
# --------------------------------------------------------------------- #

class TestDeleteExpenseMethodGuard:
    def test_get_delete_returns_405_and_does_not_delete(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)

        response = client.get(f"/expenses/{expense_id}/delete")
        assert response.status_code == 405, (
            "The delete route only accepts POST; a bare GET/link click must not "
            "be able to trigger a deletion"
        )

        untouched = db.get_expense_by_id(expense_id)
        assert untouched is not None, "GET must not delete the expense"
        assert untouched["amount"] == 50.0
        assert untouched["category"] == "Food"

    def test_get_delete_returns_405_even_for_nonexistent_id(self, client, empty_user):
        """Method dispatch happens before any ownership/existence lookup."""
        login(client, empty_user)
        response = client.get("/expenses/999999/delete")
        assert response.status_code == 405


# --------------------------------------------------------------------- #
# POST — successful deletion                                            #
# --------------------------------------------------------------------- #

class TestDeleteExpensePostSuccess:
    def test_post_delete_own_expense_redirects_to_profile(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)

        response = client.post(f"/expenses/{expense_id}/delete")
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_post_delete_own_expense_removes_row_from_db(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)

        client.post(f"/expenses/{expense_id}/delete")

        deleted = db.get_expense_by_id(expense_id)
        assert deleted is None, "Expense row must be gone from the database after deletion"

    def test_post_delete_does_not_render_profile_directly(self, client, empty_user):
        """On success the view must redirect (302), never render profile.html inline."""
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)

        with captured_templates(flask_app) as templates:
            response = client.post(f"/expenses/{expense_id}/delete", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers.get("Location") is not None
        assert not templates, (
            "The delete view must redirect, not render profile.html (or any template) directly"
        )


# --------------------------------------------------------------------- #
# Profile integration — recent transactions / summary / breakdown        #
# --------------------------------------------------------------------- #

class TestDeleteExpenseProfileIntegration:
    def test_deleted_expense_no_longer_in_recent_transactions(self, client, empty_user):
        expense_id = create_expense_for(
            empty_user, amount=50.0, category="Food",
            expense_date="2024-01-15", description="Groceries",
        )
        login(client, empty_user)
        client.post(f"/expenses/{expense_id}/delete")

        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert "Groceries" not in body, "Deleted expense's description must no longer show on /profile"

    def test_summary_stats_reflect_deletion(self, client, empty_user):
        first_id = create_expense_for(
            empty_user, amount=50.0, category="Food",
            expense_date="2024-01-15", description="Groceries",
        )
        create_expense_for(
            empty_user, amount=30.0, category="Transport",
            expense_date="2024-01-16", description="Bus fare",
        )
        login(client, empty_user)

        before = client.get("/profile").get_data(as_text=True)
        assert "80" in before or "80.0" in before or "80.00" in before, (
            "Sanity check: total spent should reflect both seeded expenses before deletion"
        )

        client.post(f"/expenses/{first_id}/delete")

        after = client.get("/profile").get_data(as_text=True)
        assert "80.0" not in after and "80.00" not in after, (
            "Total spent must drop after deletion and no longer include the deleted amount"
        )
        assert "30.0" in after or "30.00" in after, (
            "Remaining expense's amount should still feed the summary stats"
        )

    def test_category_breakdown_reflects_deletion(self, client, empty_user):
        health_id = create_expense_for(
            empty_user, amount=20.0, category="Health",
            expense_date="2024-01-15", description="Pharmacy",
        )
        create_expense_for(
            empty_user, amount=10.0, category="Entertainment",
            expense_date="2024-01-16", description="Movie",
        )
        login(client, empty_user)

        client.post(f"/expenses/{health_id}/delete")

        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert "Health" not in body, "Deleted expense's category must no longer appear in the breakdown"
        assert "Entertainment" in body, "Remaining expense's category should still appear in the breakdown"

    def test_profile_recent_transactions_row_has_delete_form_for_expense(
        self, client, empty_user
    ):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)

        response = client.get("/profile")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"/expenses/{expense_id}/delete" in body, (
            "Expected /profile to contain a working delete control (POST form) "
            "targeting the correct expense"
        )


# --------------------------------------------------------------------- #
# Isolation — deleting one expense must not affect any other row         #
# --------------------------------------------------------------------- #

class TestDeleteExpenseIsolation:
    def test_deleting_one_expense_leaves_other_expenses_of_same_user_untouched(
        self, client, empty_user
    ):
        keep_id_1 = create_expense_for(
            empty_user, amount=10.0, category="Food", expense_date="2024-01-01",
            description="Keep me 1",
        )
        target_id = create_expense_for(
            empty_user, amount=20.0, category="Transport", expense_date="2024-01-02",
            description="Delete me",
        )
        keep_id_2 = create_expense_for(
            empty_user, amount=30.0, category="Bills", expense_date="2024-01-03",
            description="Keep me 2",
        )
        login(client, empty_user)

        response = client.post(f"/expenses/{target_id}/delete")
        assert response.status_code == 302

        assert db.get_expense_by_id(target_id) is None
        remaining_1 = db.get_expense_by_id(keep_id_1)
        remaining_2 = db.get_expense_by_id(keep_id_2)
        assert remaining_1 is not None and remaining_1["description"] == "Keep me 1"
        assert remaining_2 is not None and remaining_2["description"] == "Keep me 2"
        assert count_expenses_for(empty_user) == 2, "Only the targeted row should have been removed"

    def test_deleting_one_users_expense_does_not_affect_another_users_expenses(
        self, client, demo_user, empty_user
    ):
        own_expense_id = create_expense_for(
            empty_user, amount=15.0, category="Food", description="My groceries"
        )
        demo_count_before = count_expenses_for(demo_user["id"])
        assert demo_count_before > 0, "Expected the seeded demo user to have expenses"

        login(client, empty_user)
        response = client.post(f"/expenses/{own_expense_id}/delete")
        assert response.status_code == 302

        assert db.get_expense_by_id(own_expense_id) is None
        assert count_expenses_for(demo_user["id"]) == demo_count_before, (
            "Deleting one user's expense must not remove any rows belonging to another user"
        )
