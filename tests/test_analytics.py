"""
Tests for the "Analytics" Coming Soon feature.

Spec covered (see task description — written before/without reading app.py):

- GET /analytics is protected by the same `login_required` decorator used on
  /profile: it checks `session.get("user_id")` and redirects (302) to
  `url_for("login")` (i.e. "/login") when absent.
- A logged-in user (session contains "user_id") visiting /analytics gets a
  200 response rendering `templates/analytics.html` — a static Coming Soon
  placeholder with no dynamic data.
- base.html's navbar shows an "Analytics" link only when `session.user_id`
  is set; logged-out visitors must not see it on any page extending
  base.html (e.g. the landing page "/", the "/login" page).
- While on /analytics, the "Analytics" nav link carries an `active` CSS
  class (via `request.endpoint == 'analytics'`); on other pages (e.g.
  /profile, "/") it must not.

These tests reuse the `client`, `temp_db`, `demo_user`, and `empty_user`
fixtures defined in tests/conftest.py.
"""

import re
from contextlib import contextmanager

from flask import template_rendered

from app import app as flask_app


# --------------------------------------------------------------------- #
# Helpers                                                                #
# --------------------------------------------------------------------- #

def login(client, user_id):
    """Fake a logged-in session the same way other tests in this suite do."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


@contextmanager
def captured_templates(app):
    """Record the names of templates rendered during the `with` block.

    Used to assert that a specific template file was rendered, rather than
    just inferring it from response body text.
    """
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append(template.name)

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)


def find_anchor_tag(body, href):
    """
    Return the full opening <a ...> tag whose href matches `href` exactly
    (attribute order independent), or None if no such link exists anywhere
    in `body`.
    """
    pattern = re.compile(
        r'<a\b[^>]*href=["\']' + re.escape(href) + r'["\'][^>]*>',
        re.IGNORECASE,
    )
    match = pattern.search(body)
    return match.group(0) if match else None


def find_anchor_text(body, href):
    """Return the inner text of the first <a href="{href}">...</a> found."""
    pattern = re.compile(
        r'<a\b[^>]*href=["\']' + re.escape(href) + r'["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(body)
    return match.group(1).strip() if match else None


def anchor_has_class(tag, css_class):
    """Check whether an opening <a ...> tag's class attribute contains css_class."""
    match = re.search(r'class=["\']([^"\']*)["\']', tag, re.IGNORECASE)
    if not match:
        return False
    return css_class in match.group(1).split()


# --------------------------------------------------------------------- #
# Auth guard                                                             #
# --------------------------------------------------------------------- #

class TestAnalyticsAuthGuard:
    def test_analytics_requires_login_redirects(self, client):
        response = client.get("/analytics")
        assert response.status_code == 302, "Unauthenticated request must redirect"
        assert "/login" in response.headers["Location"], "Must redirect to /login"

    def test_analytics_logged_out_response_has_no_analytics_content(self, client):
        response = client.get("/analytics")
        body = response.get_data(as_text=True)
        assert "coming soon" not in body.lower(), (
            "A 302 redirect response must not leak analytics.html content"
        )


# --------------------------------------------------------------------- #
# Happy path — logged-in access                                          #
# --------------------------------------------------------------------- #

class TestAnalyticsHappyPath:
    def test_analytics_returns_200_for_logged_in_user(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/analytics")
        assert response.status_code == 200, "Logged-in user must be able to reach /analytics"

    def test_analytics_renders_analytics_template(self, client, empty_user):
        login(client, empty_user)
        with captured_templates(flask_app) as templates:
            response = client.get("/analytics")
        assert response.status_code == 200
        assert templates, "Expected a template to be rendered for GET /analytics"
        assert templates[-1] == "analytics.html", (
            f"Expected templates/analytics.html to render, got {templates[-1]!r}"
        )

    def test_analytics_page_communicates_coming_soon(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/analytics")
        body = response.get_data(as_text=True)
        assert "coming soon" in body.lower(), (
            "Expected the analytics page to communicate a 'Coming Soon' placeholder state"
        )

    def test_analytics_page_is_static_no_expense_data_leaked(self, client, demo_user):
        """Per spec, /analytics has 'no dynamic data, just static content' —
        it must not surface a logged-in demo user's expense data."""
        login(client, demo_user["id"])
        response = client.get("/analytics")
        body = response.get_data(as_text=True)
        for leaked in ["Groceries", "Bus pass", "Electricity bill", "₹219.89"]:
            assert leaked not in body, (
                f"Analytics page must be static content only; unexpectedly found {leaked!r}"
            )


# --------------------------------------------------------------------- #
# Navbar visibility                                                      #
# --------------------------------------------------------------------- #

class TestAnalyticsNavVisibility:
    def test_landing_page_hides_analytics_link_when_logged_out(self, client):
        response = client.get("/")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert find_anchor_tag(body, "/analytics") is None, (
            "Logged-out landing page must not contain an Analytics nav link"
        )

    def test_login_page_hides_analytics_link_when_logged_out(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert find_anchor_tag(body, "/analytics") is None, (
            "Logged-out /login page must not contain an Analytics nav link"
        )

    def test_landing_page_shows_analytics_link_when_logged_in(self, client, empty_user):
        # "/" redirects logged-in users to /profile (pre-existing app behavior,
        # unrelated to this feature) — follow it to reach a 200 page and inspect its navbar.
        login(client, empty_user)
        response = client.get("/", follow_redirects=True)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert find_anchor_tag(body, "/analytics") is not None, (
            "Logged-in landing page must contain an Analytics nav link"
        )

    def test_profile_page_shows_analytics_link_when_logged_in(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/profile")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert find_anchor_tag(body, "/analytics") is not None, (
            "Logged-in /profile page must contain an Analytics nav link"
        )

    def test_analytics_nav_link_text_mentions_analytics(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/", follow_redirects=True)
        body = response.get_data(as_text=True)
        text = find_anchor_text(body, "/analytics")
        assert text is not None, "Expected an Analytics nav link on the logged-in landing page"
        assert "analytics" in text.lower(), (
            f"Expected the nav link text to mention Analytics, got {text!r}"
        )


# --------------------------------------------------------------------- #
# Navbar active-state indication                                         #
# --------------------------------------------------------------------- #

class TestAnalyticsNavActiveState:
    def test_analytics_nav_link_is_active_on_analytics_page(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/analytics")
        body = response.get_data(as_text=True)
        tag = find_anchor_tag(body, "/analytics")
        assert tag is not None, "Analytics nav link must be present on /analytics itself"
        assert anchor_has_class(tag, "active"), (
            "Analytics nav link must carry an 'active' class while on /analytics "
            f"(endpoint == 'analytics'); got tag: {tag!r}"
        )

    def test_analytics_nav_link_is_not_active_on_profile_page(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        tag = find_anchor_tag(body, "/analytics")
        assert tag is not None, "Analytics nav link must still be present on /profile"
        assert not anchor_has_class(tag, "active"), (
            f"Analytics nav link must NOT be active on /profile; got tag: {tag!r}"
        )

    def test_analytics_nav_link_is_not_active_on_landing_page(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/", follow_redirects=True)
        body = response.get_data(as_text=True)
        tag = find_anchor_tag(body, "/analytics")
        assert tag is not None, "Analytics nav link must still be present on the landing page"
        assert not anchor_has_class(tag, "active"), (
            f"Analytics nav link must NOT be active on '/'; got tag: {tag!r}"
        )
