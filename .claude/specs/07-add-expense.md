# Spec: Add Expense

## Overview

Step 7 implements the first write path for expenses: a form at `/expenses/add`
that lets a logged-in user record a new expense (amount, category, date,
optional description). On successful submission the expense is inserted into
the `expenses` table for the current user and the user is redirected to
`/profile`, where it immediately shows up in recent transactions, summary
stats, and the category breakdown (all of which already read from the
`expenses` table as of Step 5/6). This replaces the current stub at
`GET /expenses/add` which just returns the raw string
`"Add expense — coming in Step 7"`.

## Depends on

- Step 1: Database setup (`expenses` table must exist)
- Step 3: Login/Logout (`login_required`, `session["user_id"]`)
- Step 5: Backend connection (`/profile` already reads from `expenses` via
  `database/queries.py`, so newly added rows appear there with no further
  changes)

## Routes

- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate input, insert the expense, redirect to
  `/profile` — logged-in only

Both methods are handled by a single `add_expense()` view (same
GET/POST-branch pattern already used by `register()` and `login()`), guarded
by the existing `login_required` decorator. A logged-out user hitting either
method is redirected to `/login`.

## Database changes

No schema changes — the `expenses` table already has every column this
feature needs (`user_id`, `amount`, `category`, `date`, `description`).

New function in `database/db.py` (alongside `create_user`, following the same
connect/execute/commit/close pattern):

- `create_expense(user_id, amount, category, date, description)` — inserts one
  row into `expenses` using parameterised placeholders and returns
  `cursor.lastrowid`.

## Templates

- **Create:** `templates/add_expense.html` — extends `base.html`; a form card
  (styled like `auth-card`/`form-group`/`form-input`/`btn-submit`, already in
  `style.css`) with fields:
  - Amount — `<input type="number" step="0.01" min="0.01">`, required
  - Category — `<select>` populated from `CATEGORIES` in `database/db.py`
  - Date — `<input type="date">`, required, defaulting to today's date
  - Description — `<input type="text">`, optional
  - Submit button: "Add expense"
  - An inline error banner (same `.auth-error`-style pattern used in
    `register.html`) shown when validation fails
- **Modify:** none. (`base.html` navbar already links nowhere for this step —
  no nav change is in scope here.)

## Files to change

- `app.py`
  - Replace the `add_expense()` stub with a real `GET`/`POST` view:
    `@app.route("/expenses/add", methods=["GET", "POST"])` +
    `@login_required`
    - `GET`: render `add_expense.html` with `categories=CATEGORIES` and
      today's date as the default value for the date field
    - `POST`: read `amount`, `category`, `date`, `description` from
      `request.form`; validate (see Rules below); on failure re-render the
      form with an `error` message (same pattern as `register()`); on success
      call `create_expense(...)` and `redirect(url_for("profile"))`
  - Import `create_expense` and `CATEGORIES` from `database.db`

## Files to create

- `templates/add_expense.html`
- `static/css/add_expense.css` — page-specific layout only (container width,
  spacing); reuses the existing global `.form-group` / `.form-input` /
  `.btn-submit` classes from `style.css` rather than redefining them

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings in SQL, even for the insert
- Passwords hashed with werkzeug (unchanged — no auth logic in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `url_for()` for every internal link and form `action` — never hardcode
  `/expenses/add` or `/profile` as literal strings in the template
- All DB logic (the new `create_expense` insert) lives in `database/db.py`,
  never inline in the `app.py` route
- Amount validation: must parse as a positive float (`> 0`); reject blank,
  non-numeric, zero, or negative values with error
  `"Please enter a valid amount greater than zero."`
- Category validation: must be one of the values in `CATEGORIES`; reject
  anything else with error `"Please select a valid category."`
- Date validation: must parse as `YYYY-MM-DD` via
  `datetime.strptime(value, "%Y-%m-%d")`; reject malformed/missing dates with
  error `"Please enter a valid date."`; future dates are allowed (no
  upper-bound check)
- Description is optional; strip whitespace; store `None`/empty string if
  blank (matches nullable `description` column)
- On any validation failure, return `200` and re-render `add_expense.html`
  with the `error` message — never redirect on failure, never lose the page
- On success, redirect (`302`) to `/profile` — never render `profile.html`
  directly from this view

## Definition of done

- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in shows a form with Amount,
      Category (dropdown of all 7 categories), Date (defaulted to today), and
      Description fields
- [ ] Submitting valid data creates a new row in `expenses` for the current
      user and redirects to `/profile`
- [ ] The newly added expense immediately appears in `/profile`'s recent
      transactions, summary stats, and category breakdown without any other
      change
- [ ] Submitting a blank or non-numeric amount re-shows the form with
      "Please enter a valid amount greater than zero." and does not touch the
      database
- [ ] Submitting `amount=0` or a negative amount is rejected with the same
      error
- [ ] Submitting a category not in `CATEGORIES` is rejected with "Please
      select a valid category."
- [ ] Submitting a malformed or missing date is rejected with "Please enter a
      valid date." and does not crash the app
- [ ] Leaving Description blank succeeds (it is optional)
- [ ] A logged-in user cannot add an expense to another user's account — the
      new row's `user_id` always comes from `session["user_id"]`, never from
      form input
