"""
Tests for the "Edit Expense" feature (Step 8).

Spec covered — see .claude/specs/08-edit-expense.md (written from the spec's
"Routes", "Rules for implementation", and "Definition of done" sections, not
by reading app.py/database/db.py's implementation):

- `GET /expenses/<id>/edit` and `POST /expenses/<id>/edit` are guarded by the
  same `login_required` pattern as `/profile` and `/analytics`: a logged-out
  request redirects (302) to `/login`.
- If the expense id does not exist, or exists but belongs to a different
  user, the view must `abort(404)` — never redirect, never leak whether the
  id belongs to someone else.
- `GET` for an owned expense renders a form pre-filled with the expense's
  current amount, category, date, and description.
- `POST` with valid data updates the *existing* row (same id, no new row)
  and redirects (302) to `/profile`.
- Validation reuses the add-expense rules:
    * amount must parse as a positive float (`> 0`); blank/non-numeric/
      zero/negative amounts are rejected with
      "Please enter a valid amount greater than zero."
    * category must be one of `CATEGORIES`; anything else is rejected with
      "Please select a valid category."
    * date must parse as `YYYY-MM-DD`; malformed/missing dates are rejected
      with "Please enter a valid date." and must not crash the app (no 500).
    * description is optional; blank descriptions succeed.
- On any validation failure: HTTP 200, `edit_expense.html` re-rendered with
  the `error` message, and the database row is left unmodified.
- On success: updated values must immediately be reflected on `/profile`
  (recent transactions, summary stats, category breakdown).
- Ownership is enforced server-side using the path id + session user, never
  a client-supplied field — a user cannot update another user's expense by
  guessing/incrementing the id or by including a tampered `user_id` in the
  submitted form.
- Each row in `/profile`'s recent-transactions table has a working "Edit"
  link pointing at the correct expense.

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


VALID_PAYLOAD = {
    "amount": "42.50",
    "category": "Health",
    "date": "2024-03-10",
    "description": "Doctor visit",
}


# --------------------------------------------------------------------- #
# Auth guard                                                             #
# --------------------------------------------------------------------- #

class TestEditExpenseAuthGuard:
    def test_get_edit_requires_login_redirects_to_login(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        response = client.get(f"/expenses/{expense_id}/edit")
        assert response.status_code == 302, "Logged-out GET must redirect, not render the form"
        assert "/login" in response.headers["Location"], "Must redirect to /login"

    def test_post_edit_requires_login_redirects_to_login(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        response = client.post(f"/expenses/{expense_id}/edit", data=VALID_PAYLOAD)
        assert response.status_code == 302, "Logged-out POST must redirect, not update the DB"
        assert "/login" in response.headers["Location"], "Must redirect to /login"

        # The DB must be untouched by an unauthenticated attempt.
        expense = db.get_expense_by_id(expense_id)
        assert expense["amount"] == 50.0
        assert expense["category"] == "Food"


# --------------------------------------------------------------------- #
# 404 — nonexistent id / other user's expense                           #
# --------------------------------------------------------------------- #

class TestEditExpenseNotFound:
    def test_get_edit_nonexistent_id_returns_404(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/expenses/999999/edit")
        assert response.status_code == 404

    def test_post_edit_nonexistent_id_returns_404(self, client, empty_user):
        login(client, empty_user)
        response = client.post("/expenses/999999/edit", data=VALID_PAYLOAD)
        assert response.status_code == 404

    def test_get_edit_other_users_expense_returns_404_not_form_not_redirect(
        self, client, demo_user, empty_user
    ):
        # demo_user is seeded with expenses; empty_user tries to view one of them.
        demo_expenses = db.get_db()
        row = demo_expenses.execute(
            "SELECT id FROM expenses WHERE user_id = ? LIMIT 1", (demo_user["id"],)
        ).fetchone()
        demo_expenses.close()
        assert row is not None, "Expected the seeded demo user to have at least one expense"
        other_expense_id = row["id"]

        login(client, empty_user)
        response = client.get(f"/expenses/{other_expense_id}/edit")
        assert response.status_code == 404, (
            "Must be a 404, never the edit form and never a redirect, "
            "so existence of another user's id isn't leaked"
        )

    def test_post_edit_other_users_expense_returns_404_and_does_not_modify_db(
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
        response = client.post(f"/expenses/{other_expense_id}/edit", data=VALID_PAYLOAD)
        assert response.status_code == 404

        untouched = db.get_expense_by_id(other_expense_id)
        assert untouched["amount"] == original_amount, "Another user's expense must not be modified"
        assert untouched["category"] == original_category


# --------------------------------------------------------------------- #
# GET — pre-filled form for an owned expense                            #
# --------------------------------------------------------------------- #

class TestEditExpenseGetPrefill:
    def test_get_edit_own_expense_returns_200(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)
        response = client.get(f"/expenses/{expense_id}/edit")
        assert response.status_code == 200

    def test_get_edit_own_expense_renders_edit_template(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)
        with captured_templates(flask_app) as templates:
            response = client.get(f"/expenses/{expense_id}/edit")
        assert response.status_code == 200
        assert templates, "Expected a template to render for GET /expenses/<id>/edit"
        assert templates[-1] == "edit_expense.html"

    def test_get_edit_own_expense_prefills_amount_category_date_description(
        self, client, empty_user
    ):
        expense_id = create_expense_for(
            empty_user,
            amount=123.45,
            category="Entertainment",
            expense_date="2024-06-07",
            description="Concert tickets",
        )
        login(client, empty_user)
        response = client.get(f"/expenses/{expense_id}/edit")
        body = response.get_data(as_text=True)

        assert "123.45" in body, "Expected the current amount pre-filled in the form"
        assert "2024-06-07" in body, "Expected the current date pre-filled in the form"
        assert "Concert tickets" in body, "Expected the current description pre-filled in the form"
        assert (
            'value="Entertainment" selected' in body
            or 'selected>Entertainment' in body
            or ('selected' in body and "Entertainment" in body)
        ), "Expected the current category to be the selected <option>"


# --------------------------------------------------------------------- #
# POST — successful update                                              #
# --------------------------------------------------------------------- #

class TestEditExpensePostSuccess:
    def test_post_valid_changes_redirects_to_profile(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)
        response = client.post(f"/expenses/{expense_id}/edit", data=VALID_PAYLOAD)
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_post_valid_changes_updates_existing_row_not_a_new_row(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_PAYLOAD)

        updated = db.get_expense_by_id(expense_id)
        assert updated is not None
        assert updated["amount"] == pytest.approx(42.50)
        assert updated["category"] == "Health"
        assert updated["date"] == "2024-03-10"
        assert updated["description"] == "Doctor visit"

        conn = db.get_db()
        count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM expenses WHERE user_id = ?", (empty_user,)
        ).fetchone()["cnt"]
        conn.close()
        assert count == 1, "Edit must update the existing row, not insert a new one"

    def test_updated_values_appear_on_profile_recent_transactions(self, client, empty_user):
        expense_id = create_expense_for(
            empty_user, amount=50.0, category="Food",
            expense_date="2024-01-15", description="Groceries",
        )
        login(client, empty_user)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_PAYLOAD)

        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert "Doctor visit" in body, "Updated description must show on /profile"
        assert "Groceries" not in body, "Stale description must no longer show on /profile"
        assert "Health" in body, "Updated category must show on /profile"

    def test_updated_values_appear_in_profile_summary_and_breakdown(self, client, empty_user):
        expense_id = create_expense_for(
            empty_user, amount=50.0, category="Food",
            expense_date="2024-01-15", description="Groceries",
        )
        login(client, empty_user)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_PAYLOAD)

        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert "42.50" in body or "42.5" in body, "Updated amount must feed the summary stats"
        assert "Food" not in body, "Old category must no longer appear in the breakdown"


# --------------------------------------------------------------------- #
# POST — validation failures                                            #
# --------------------------------------------------------------------- #

class TestEditExpenseValidation:
    @pytest.mark.parametrize("bad_amount", ["", "abc", "0", "-5", "-0.01"])
    def test_post_invalid_amount_rejected_and_db_unchanged(self, client, empty_user, bad_amount):
        expense_id = create_expense_for(empty_user, amount=50.0, category="Food")
        login(client, empty_user)

        payload = dict(VALID_PAYLOAD, amount=bad_amount)
        response = client.post(f"/expenses/{expense_id}/edit", data=payload)

        assert response.status_code == 200, "Validation failure must re-render, not redirect"
        body = response.get_data(as_text=True)
        assert "Please enter a valid amount greater than zero." in body

        unchanged = db.get_expense_by_id(expense_id)
        assert unchanged["amount"] == 50.0
        assert unchanged["category"] == "Food"

    def test_post_invalid_amount_rerenders_edit_template(self, client, empty_user):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)
        payload = dict(VALID_PAYLOAD, amount="not-a-number")

        with captured_templates(flask_app) as templates:
            response = client.post(f"/expenses/{expense_id}/edit", data=payload)

        assert response.status_code == 200
        assert templates and templates[-1] == "edit_expense.html", (
            "On failure, must never redirect or lose the page — must re-render edit_expense.html"
        )

    def test_post_invalid_category_rejected_and_db_unchanged(self, client, empty_user):
        expense_id = create_expense_for(empty_user, amount=50.0, category="Food")
        login(client, empty_user)

        payload = dict(VALID_PAYLOAD, category="NotARealCategory")
        response = client.post(f"/expenses/{expense_id}/edit", data=payload)

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Please select a valid category." in body

        unchanged = db.get_expense_by_id(expense_id)
        assert unchanged["category"] == "Food"
        assert unchanged["amount"] == 50.0

    @pytest.mark.parametrize(
        "bad_date", ["", "2024/03/10", "not-a-date", "10-03-2024", "2024-13-40"]
    )
    def test_post_invalid_date_rejected_and_does_not_crash(self, client, empty_user, bad_date):
        expense_id = create_expense_for(
            empty_user, amount=50.0, category="Food", expense_date="2024-01-15"
        )
        login(client, empty_user)

        payload = dict(VALID_PAYLOAD, date=bad_date)
        response = client.post(f"/expenses/{expense_id}/edit", data=payload)

        assert response.status_code == 200, "Bad date must not crash the app (no 500)"
        body = response.get_data(as_text=True)
        assert "Please enter a valid date." in body

        unchanged = db.get_expense_by_id(expense_id)
        assert unchanged["date"] == "2024-01-15", "DB row must be untouched on validation failure"

    def test_post_blank_description_succeeds(self, client, empty_user):
        expense_id = create_expense_for(
            empty_user, amount=50.0, category="Food",
            expense_date="2024-01-15", description="Groceries",
        )
        login(client, empty_user)

        payload = dict(VALID_PAYLOAD, description="")
        response = client.post(f"/expenses/{expense_id}/edit", data=payload)

        assert response.status_code == 302, "Blank description is optional and must succeed"
        assert "/profile" in response.headers["Location"]

        updated = db.get_expense_by_id(expense_id)
        assert not updated["description"], (
            "Blank description should be stored as None/empty, not the stale value"
        )
        assert updated["amount"] == pytest.approx(42.50)


# --------------------------------------------------------------------- #
# Ownership enforcement — server-side, not trusting client input        #
# --------------------------------------------------------------------- #

class TestEditExpenseOwnershipEnforcement:
    def test_cannot_update_another_users_expense_via_form_tampering(
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
        original_date = row["date"]
        original_description = row["description"]

        # Logged in as a different user, attempt to overwrite the other
        # user's expense — even trying to smuggle a `user_id` field into
        # the form to see if ownership can be reassigned client-side.
        login(client, empty_user)
        tampered_payload = dict(VALID_PAYLOAD, user_id=str(demo_user["id"]))
        response = client.post(f"/expenses/{other_expense_id}/edit", data=tampered_payload)

        assert response.status_code == 404, (
            "Ownership must be enforced server-side via session + path id; "
            "a foreign expense id must 404 regardless of form contents"
        )

        untouched = db.get_expense_by_id(other_expense_id)
        assert untouched["amount"] == original_amount
        assert untouched["category"] == original_category
        assert untouched["date"] == original_date
        assert untouched["description"] == original_description

    def test_owner_can_still_edit_their_own_expense_after_tampering_attempt(
        self, client, empty_user
    ):
        """Sanity check: the ownership guard doesn't block legitimate self-edits."""
        expense_id = create_expense_for(empty_user, amount=10.0, category="Other")
        login(client, empty_user)

        response = client.post(f"/expenses/{expense_id}/edit", data=VALID_PAYLOAD)
        assert response.status_code == 302

        updated = db.get_expense_by_id(expense_id)
        assert updated["amount"] == pytest.approx(42.50)


# --------------------------------------------------------------------- #
# Profile integration — the per-row Edit link                           #
# --------------------------------------------------------------------- #

class TestEditExpenseProfileIntegration:
    def test_profile_recent_transactions_row_has_edit_link_to_correct_expense(
        self, client, empty_user
    ):
        expense_id = create_expense_for(empty_user)
        login(client, empty_user)

        response = client.get("/profile")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"/expenses/{expense_id}/edit" in body, (
            "Expected /profile to contain a working Edit link for the transaction"
        )
