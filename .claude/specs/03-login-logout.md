# Spec: Login and Logout

## Overview

This step lets a registered user actually sign back in and out of Spendly.
`GET /login` already renders `login.html` with a working form, but there is
no `POST /login` handler, so submitting it does nothing. `GET /logout` is
still a stub returning a placeholder string. This step adds real
authentication: verifying email/password against the `users` table
(populated by registration, Step 2) and establishing the same
`session["user_id"]` convention Step 2 introduced, plus a real logout that
clears it. This is the step that makes the login ↔ logout ↔ registration
loop functionally complete, ahead of Step 4 (profile) actually gating access
on being logged in.

## Depends on

- Step 1 — Database setup: `users` table, `get_db()`.
- Step 2 — Registration: `session["user_id"]` convention, and
  `get_user_by_email(email)` in `database/db.py` (already exists, reused
  here rather than duplicated).

## Routes

- `POST /login` — validates email/password against the `users` table,
  starts a session on success, redirects to `/profile` — re-renders
  `login.html` with an inline error on failure — public
- `GET /login` — no change, already implemented
- `GET /logout` — clears the session and redirects to `/login` — logged-in
  (safe to call when not logged in too — it's a no-op clear either way)

## Database changes

No database changes. `get_user_by_email(email)` already exists in
`database/db.py` (added in Step 2) and is reused here — no new helper
needed for the lookup itself.

## Templates

- **Create:** none
- **Modify:** none — `login.html` already posts to `/login`, already
  renders `{{ error }}` via the `auth-error` block, and already has
  `email` / `password` fields wired up. No template changes required.

## Files to change

- `app.py` — add `POST` to the `/login` route's methods, add the handler
  logic (read form data, look up user, verify password hash, set session,
  redirect or re-render with error); implement `/logout` for real (clear
  the session, redirect) instead of returning its placeholder string

## Files to create

- None

## New dependencies

No new dependencies. `check_password_hash` is already part of
`werkzeug.security` (same module `generate_password_hash` comes from,
already used in Step 2 and in `seed_db()`).

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords verified with werkzeug (`check_password_hash`) — never compare
  plaintext passwords directly
- Use CSS variables — never hardcode hex values (no template/CSS changes
  expected, but if any styling is touched, follow this)
- All templates extend `base.html`
- DB logic stays in `database/db.py` only — reuse `get_user_by_email`
  rather than writing a new inline query in `app.py`
- Use one generic error message ("Invalid email or password.") for both
  "no such user" and "wrong password" — never reveal which one it was,
  to avoid leaking whether an email is registered (user enumeration)
- Do not implement `/profile`, `/expenses/add`, or any other still-stub
  route as part of this step — redirecting to `/profile` after login is
  fine even though that route still returns its Step 4 placeholder string
- Do not add a `login_required` decorator or gate any route on session
  state in this step — no route currently checks for a logged-in session,
  and adding that gate is out of scope until Step 4 needs it
- Keep `/logout` as `GET` (matching its existing route decorator) rather
  than introducing a POST-only logout form — this is a deliberate scope
  choice for a tutorial-sized app with no CSRF tooling in place, not an
  oversight

## Definition of done

- [ ] Visiting `/login` still shows the existing form (unchanged)
- [ ] Submitting the correct email/password for a registered user (e.g.
      the demo user or one created via Step 2's registration flow) sets a
      session and redirects to `/profile`
- [ ] Submitting a correct email with the wrong password shows the generic
      inline error and does not set a session
- [ ] Submitting an email that has no matching user shows the same generic
      inline error (identical wording to the wrong-password case)
- [ ] Submitting with a missing email or missing password shows an inline
      error and does not query with empty values as if they were valid
- [ ] Visiting `/logout` after being logged in clears the session (a
      subsequent request no longer carries a valid `user_id` in session)
      and redirects to `/login`
- [ ] Visiting `/logout` while not logged in does not error — it just
      redirects to `/login`
- [ ] All queries triggered by this step use parameterized SQL (verify by
      reading the `app.py` diff — no new raw SQL should be added here at
      all, since `get_user_by_email` is reused)
- [ ] App still starts cleanly on port 5001
