# Spec: Delete Expense

## Overview

Step 9 replaces the stub at `GET /expenses/<id>/delete` (currently the raw
string `"Delete expense — coming in Step 9"`) with a real delete flow: a
logged-in user can remove one of their own expenses from a row on
`/profile`. This is the third and final write path after Step 7 (add) and
Step 8 (edit), and completes full CRUD on the `expenses` table. Unlike
add/edit there is no form to fill in — the action is destructive, so it is
submitted as a `POST` (never a `GET`, which must not mutate state) and
gated behind a client-side JS confirmation dialog so a stray click can't
silently delete data.

## Depends on

- Step 1: Database setup (`expenses` table must exist)
- Step 3: Login/Logout (`login_required`, `session["user_id"]`)
- Step 5: Backend connection (`/profile` reads transactions via
  `database/queries.py`)
- Step 8: Edit expense (`get_expense_by_id` for the ownership-check
  pattern; the `row-action-link` styling and per-row actions cell in
  `profile.html`/`profile.css` are reused here)

## Routes

- `POST /expenses/<id>/delete` — delete the expense, redirect to
  `/profile` — logged-in only, must own the expense

No `GET` handler is added for this path — deleting is a mutation and must
never happen as a side effect of a `GET` request or a bare link click.

## Database changes

No schema changes — deleting a row needs no new columns.

New function in `database/db.py` (same connect/execute/commit/close
pattern as `create_expense`/`update_expense`):

- `delete_expense(expense_id)` — `DELETE FROM expenses WHERE id = ?`,
  parameterised, no return value needed

## Templates

- **Modify:** `templates/profile.html` — in the actions cell of each
  recent-transactions row, add a small `POST` form (next to the existing
  edit link) whose `action` is `{{ url_for('delete_expense', id=tx.id) }}`
  and whose submit button carries a class (e.g. `delete-expense-form`)
  that `main.js` binds a confirm dialog to before letting the submit
  through

## Files to change

- `app.py`
  - Replace the `delete_expense(id)` stub with a real view:
    `@app.route("/expenses/<int:id>/delete", methods=["POST"])` +
    `@login_required`
    - Look up the expense via `get_expense_by_id(id)`; `abort(404)` if
      missing or if `expense["user_id"] != session["user_id"]`
    - Call `delete_expense(id)`, flash a confirmation message, and
      `redirect(url_for("profile"))`
  - Import `delete_expense` from `database.db`
- `database/db.py` — add `delete_expense`
- `templates/profile.html` — add the per-row delete form/button in the
  actions cell
- `static/css/profile.css` — style the delete button consistently with
  the existing `row-action-link` pattern (e.g. a `danger` hover color),
  and make sure a `<button>` inside a form matches the visual size/
  alignment of the existing `<a>` edit icon
- `static/js/main.js` — add a small vanilla-JS confirm-before-submit
  handler: listen for `submit` on forms with the delete class, call
  `confirm("Delete this expense? This cannot be undone.")`, and
  `event.preventDefault()` if the user cancels

## Files to create

None.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings in SQL, even for the
  delete
- Passwords hashed with werkzeug (unchanged — no auth logic in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `url_for()` for every internal link and form `action` — never hardcode
  `/expenses/<id>/delete` or `/profile` as literal strings
- All DB logic (`delete_expense`) lives in `database/db.py`, never inline
  in the `app.py` route
- The route only accepts `POST` — no `GET` handler, so the delete can
  never be triggered by a plain link, browser prefetch, or crawler
- Ownership check is mandatory: a user must never be able to delete
  another user's expense by guessing/incrementing the id — use
  `abort(404)`, not a redirect, so existence of other users' ids isn't
  leaked
- If the expense id does not exist at all, also `abort(404)`
- The confirmation dialog is a UX safeguard only, not a security
  control — the server-side ownership/existence checks are what actually
  protect the data
- On success, redirect (`302`) to `/profile` — never render `profile.html`
  directly from this view
- Deleting must not affect other users' expenses or other rows belonging
  to the same user

## Definition of done

- [ ] Submitting `POST /expenses/<id>/delete` while logged out redirects
      to `/login`
- [ ] Submitting `POST /expenses/<id>/delete` for an expense that doesn't
      exist returns a 404
- [ ] Submitting `POST /expenses/<id>/delete` for another user's expense
      returns a 404 (not a redirect) and does not delete it
- [ ] Submitting `POST /expenses/<id>/delete` for your own expense removes
      it from the database and redirects to `/profile`
- [ ] After deletion, the expense no longer appears in `/profile`'s recent
      transactions, and summary stats and category breakdown update to
      reflect its removal
- [ ] A `GET` request to `/expenses/<id>/delete` does not delete anything
      (the route only accepts `POST`)
- [ ] Deleting one expense does not affect any other expense row, for the
      same user or any other user
- [ ] Each row in `/profile`'s recent-transactions table has a working
      delete control that shows a JS confirmation dialog before
      submitting, and cancelling the dialog leaves the expense untouched
- [ ] Confirming the dialog deletes the expense and returns the user to
      an up-to-date `/profile`
