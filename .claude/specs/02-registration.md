# Spec: Registration

## Overview

This step implements real account creation for Spendly. `GET /register` already
renders `register.html` with a working form, but submitting it does nothing —
there is no `POST /register` handler. This step adds that handler: it
validates the submitted name/email/password, hashes the password, inserts a
new row into `users`, starts a logged-in session, and redirects the new user
onward. This is the first step that turns the `users` table (built in
Step 1 — database setup) into something a real visitor can populate, and it
establishes the session mechanism that later steps (login, logout, profile)
will depend on.

## Depends on

- Step 1 — Database setup: `users` table, `get_db()`, `init_db()`, and the
  `generate_password_hash` pattern must already exist in `database/db.py`.

## Routes

- `POST /register` — validates and creates a new user account, starts a
  session, redirects to `/profile` on success, re-renders `register.html`
  with an inline error on failure — public
- `GET /register` — no change, already implemented

## Database changes

No database changes. The existing `users` table
(`id, name, email, password_hash, created_at`) already supports registration.
No new columns or constraints are needed.

## Templates

- **Create:** none
- **Modify:** none — `register.html` already posts to `/register`, already
  renders `{{ error }}` via the `auth-error` block, and already has
  `name` / `email` / `password` fields wired up. No template changes required.

## Files to change

- `app.py` — add `POST` to the `/register` route's methods, add the
  handler logic (read form data, validate, call the new DB helper, set
  session, redirect or re-render with error); add `app.secret_key` so
  Flask sessions work
- `database/db.py` — add a `create_user(name, email, password_hash)` helper
  (or equivalent) that inserts into `users` and returns the new row's id;
  keep this logic out of `app.py` per project convention

## Files to create

- None

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with werkzeug (`generate_password_hash`) — never store
  or log a plaintext password
- Use CSS variables — never hardcode hex values (no template/CSS changes
  expected, but if any styling is touched, follow this)
- All templates extend `base.html`
- DB logic lives in `database/db.py` only — the route function in `app.py`
  should just read form data, call the helper, and decide what to render
- Validate on the server even though the form has `required`/`type=email`
  HTML attributes — those are trivially bypassed
- Duplicate email must be caught and shown as an inline `error` on
  `register.html`, not a raw 500 from the `UNIQUE` constraint
- Do not implement `/profile`, `/logout`, or any other stub route as part
  of this step — redirecting to `/profile` after signup is fine even though
  that route still returns its Step 4 placeholder string

## Definition of done

- [ ] Visiting `/register` still shows the existing form (unchanged)
- [ ] Submitting valid name/email/password creates exactly one new row in
      `users`, with `password_hash` populated (not the plaintext password)
- [ ] Submitting an email that already exists shows an inline error on the
      page and does not create a duplicate row
- [ ] Submitting with a missing name, invalid email format, or a password
      under 8 characters shows an inline error and does not touch the database
- [ ] After a successful registration, the response is a redirect to
      `/profile` and the session is set (a subsequent request from the same
      browser is recognized as logged in)
- [ ] Restarting the app (`python app.py`) does not lose previously
      registered users — they persist in `expense_tracker.db`
- [ ] All new SQL in `database/db.py` uses `?` placeholders, no string
      formatting
- [ ] App still starts cleanly on port 5001
