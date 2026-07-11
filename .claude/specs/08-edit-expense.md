# Spec: Edit Expense

## Overview

Step 8 replaces the stub at `GET /expenses/<id>/edit` (currently the raw
string `"Edit expense — coming in Step 8"`) with a real edit flow: a
logged-in user can open an existing expense in a pre-filled form, change its
amount, category, date, and/or description, and save the update back to the
`expenses` table. This is the second write path after Step 7's add-expense
flow, and reuses the same validation rules and form styling. Each recent
transaction row on `/profile` gets an "Edit" link so the feature is reachable
from the UI, not just by hitting the URL directly.

## Depends on

- Step 1: Database setup (`expenses` table must exist)
- Step 3: Login/Logout (`login_required`, `session["user_id"]`)
- Step 5: Backend connection (`/profile` reads transactions via
  `database/queries.py`)
- Step 7: Add expense (`create_expense`, `add_expense.html`, and the
  validation rules for amount/category/date are reused here)

## Routes

- `GET /expenses/<id>/edit` — render the edit form pre-filled with the
  expense's current values — logged-in only, must own the expense
- `POST /expenses/<id>/edit` — validate input, update the expense, redirect
  to `/profile` — logged-in only, must own the expense

Both methods are handled by a single `edit_expense(id)` view (same
GET/POST-branch pattern as `add_expense()`), guarded by `login_required`.
A logged-out user is redirected to `/login`. If the expense does not exist,
or exists but belongs to a different user, `abort(404)` — never reveal
whether the id belongs to someone else.

## Database changes

No schema changes — the `expenses` table already has every column this
feature needs.

New functions in `database/db.py` (same connect/execute/commit/close
pattern as `create_expense`):

- `get_expense_by_id(expense_id)` — `SELECT * FROM expenses WHERE id = ?`,
  returns the row (as a dict-like `sqlite3.Row`) or `None`
- `update_expense(expense_id, amount, category, expense_date, description)`
  — `UPDATE expenses SET amount = ?, category = ?, date = ?,
  description = ? WHERE id = ?`, parameterised, no return value needed

`database/queries.py` change:

- `get_recent_transactions` must also select and return `id` in each
  transaction dict (currently omits it), so `profile.html` can build the
  per-row edit link. This is additive — no existing caller breaks.

## Templates

- **Create:** `templates/edit_expense.html` — extends `base.html`; same
  form markup/classes as `add_expense.html` (`auth-card`, `form-group`,
  `form-input`, `btn-submit`), but:
  - Title: "Edit expense"
  - Fields pre-filled from the existing expense (`value="{{ expense.amount
    }}"`, selected `<option>` matching `expense.category`, `value=
    "{{ expense.date }}"` for date, `value="{{ expense.description }}"`)
  - Submit button: "Save changes"
- **Modify:** `templates/profile.html` — add an "Edit" link/icon on each
  row of the recent-transactions table, pointing to
  `{{ url_for('edit_expense', id=tx.id) }}`

## Files to change

- `app.py`
  - Replace the `edit_expense(id)` stub with a real `GET`/`POST` view:
    `@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])` +
    `@login_required`
    - Look up the expense via `get_expense_by_id(id)`; `abort(404)` if
      missing or if `expense["user_id"] != session["user_id"]`
    - `GET`: render `edit_expense.html` with the expense's current values
      and `categories=CATEGORIES`
    - `POST`: read `amount`, `category`, `date`, `description` from
      `request.form`; validate using the same rules as `add_expense`; on
      failure re-render the form with an `error` message and the
      submitted (not the stale DB) values; on success call
      `update_expense(...)` and `redirect(url_for("profile"))`
  - Import `get_expense_by_id`, `update_expense`, and `abort` (from
    `flask`)
- `database/db.py` — add `get_expense_by_id` and `update_expense`
- `database/queries.py` — add `id` to the dict returned per row in
  `get_recent_transactions`
- `templates/profile.html` — add the per-row "Edit" link in the
  transactions table

## Files to create

- `templates/edit_expense.html`

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings in SQL, even for the update
- Passwords hashed with werkzeug (unchanged — no auth logic in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `url_for()` for every internal link and form `action` — never hardcode
  `/expenses/<id>/edit` or `/profile` as literal strings
- All DB logic (`get_expense_by_id`, `update_expense`) lives in
  `database/db.py`, never inline in the `app.py` route
- Ownership check is mandatory: a user must never be able to view or update
  another user's expense by guessing/incrementing the id — use `abort(404)`,
  not a redirect, so existence of other users' ids isn't leaked
- Amount validation: must parse as a positive float (`> 0`); reject blank,
  non-numeric, zero, or negative values with error
  `"Please enter a valid amount greater than zero."`
- Category validation: must be one of the values in `CATEGORIES`; reject
  anything else with error `"Please select a valid category."`
- Date validation: must parse as `YYYY-MM-DD` via
  `datetime.strptime(value, "%Y-%m-%d")`; reject malformed/missing dates
  with error `"Please enter a valid date."`; future dates are allowed
- Description is optional; strip whitespace; store `None`/empty string if
  blank
- On any validation failure, return `200` and re-render `edit_expense.html`
  with the `error` message — never redirect on failure, never lose the
  page or the user's in-progress edits
- On success, redirect (`302`) to `/profile` — never render `profile.html`
  directly from this view

## Definition of done

- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for an expense that doesn't exist
      returns a 404
- [ ] Visiting `/expenses/<id>/edit` for another user's expense returns a
      404 (not the form, not a redirect)
- [ ] Visiting `/expenses/<id>/edit` for your own expense shows a form
      pre-filled with its current amount, category, date, and description
- [ ] Submitting valid changes updates the existing row (not a new row) and
      redirects to `/profile`
- [ ] The updated values immediately appear in `/profile`'s recent
      transactions, summary stats, and category breakdown
- [ ] Submitting a blank or non-numeric amount re-shows the form with
      "Please enter a valid amount greater than zero." and does not modify
      the database
- [ ] Submitting `amount=0` or a negative amount is rejected with the same
      error
- [ ] Submitting a category not in `CATEGORIES` is rejected with "Please
      select a valid category."
- [ ] Submitting a malformed or missing date is rejected with "Please enter
      a valid date." and does not crash the app
- [ ] Leaving Description blank succeeds (it is optional)
- [ ] Each row in `/profile`'s recent-transactions table has a working
      "Edit" link that opens the correct expense
