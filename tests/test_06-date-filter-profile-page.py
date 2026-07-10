"""
Tests for Step 6: Date Filter for Profile Page.

Spec: .claude/specs/06-date-filter-profile-page.md

Covers:
- GET /profile accepting optional date_from/date_to query params (ISO YYYY-MM-DD,
  inclusive bounds)
- No-params behavior identical to unfiltered (Step 5) profile page
- get_summary_stats / get_recent_transactions / get_category_breakdown accepting
  optional date_from/date_to kwargs and filtering when both are given
- Malformed/missing date params silently falling back to unfiltered (no crash)
- date_from > date_to being treated as absent + flash message
- Empty-range results (0 total, 0 transactions, empty breakdown, no errors)
- Filter bar presets (This Month, Last 3 Months, Last 6 Months, All Time) with
  active-state indication and url_for-style preset links
- Auth guard on /profile with filter params
- ₹ symbol retained regardless of filter

Seeded demo_user expenses (see database/db.py seed_db(), dates are within the
*current* calendar month, y/m = today's year/month):
    day 2:  35.50  Food          "Groceries"
    day 4:  15.00  Transport     "Bus pass"
    day 6:  60.00  Bills         "Electricity bill"
    day 9:  20.00  Health        "Pharmacy"
    day 12: 12.99  Entertainment "Movie ticket"
    day 16: 45.25  Shopping      "New shoes"
    day 20:  8.75  Other         "Miscellaneous"
    day 25: 22.40  Food          "Restaurant"
Total = 219.89, count = 8, top category = Bills (60.00 is the single largest
category total).

NOTE: if "today" is early in the month such that some of the above `day N`
values are in the future relative to the seed call, seed_db() would still
insert them (it does not clamp), so all 8 rows always exist with the dates
above regardless of what day-of-month the tests run on. Boundary tests below
use dates relative to today() rather than hardcoded absolute dates to stay
valid all month long.
"""

from datetime import date, timedelta

import pytest

from database.queries import (
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def profile_url(date_from=None, date_to=None):
    params = []
    if date_from is not None:
        params.append(f"date_from={date_from}")
    if date_to is not None:
        params.append(f"date_to={date_to}")
    if not params:
        return "/profile"
    return "/profile?" + "&".join(params)


# --------------------------------------------------------------------- #
# Auth guard                                                            #
# --------------------------------------------------------------------- #

class TestProfileFilterAuthGuard:
    def test_profile_with_date_params_requires_login(self, client):
        response = client.get(profile_url("2026-01-01", "2026-01-31"))
        assert response.status_code == 302, "Unauthenticated filtered request must redirect"
        assert "/login" in response.headers["Location"], "Must redirect to /login"

    def test_profile_with_malformed_date_params_requires_login(self, client):
        response = client.get(profile_url("not-a-date", "also-not-a-date"))
        assert response.status_code == 302, "Unauthenticated request must redirect even with bad params"
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------- #
# GET /profile with no params — must match unfiltered (Step 5) behavior #
# --------------------------------------------------------------------- #

class TestProfileNoParamsUnfiltered:
    def test_no_params_matches_unfiltered_demo_user(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get("/profile")
        assert response.status_code == 200

        body = response.get_data(as_text=True)
        assert "₹219.89" in body, "Unfiltered total must still be the full 219.89"
        assert "Bills" in body
        assert "Demo User" in body

    def test_no_params_all_eight_transactions_present(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        for description in [
            "Groceries", "Bus pass", "Electricity bill", "Pharmacy",
            "Movie ticket", "New shoes", "Miscellaneous", "Restaurant",
        ]:
            assert description in body, f"Expected unfiltered view to include {description}"

    def test_no_params_empty_user_shows_zero(self, client, empty_user):
        login(client, empty_user)
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert "₹0.00" in body
        assert "—" in body


# --------------------------------------------------------------------- #
# Query helper: get_summary_stats date filtering                        #
# --------------------------------------------------------------------- #

class TestGetSummaryStatsDateFilter:
    def test_no_date_args_matches_unfiltered(self, demo_user):
        stats = get_summary_stats(demo_user["id"])
        assert stats["total_spent"] == pytest.approx(219.89)
        assert stats["transaction_count"] == 8
        assert stats["top_category"] == "Bills"

    def test_full_current_month_range_includes_all_seeded_expenses(self, demo_user):
        today = date.today()
        month_start = today.replace(day=1)
        # last day of month via next-month-minus-one-day trick avoids calendar import
        if today.month == 12:
            next_month_start = date(today.year + 1, 1, 1)
        else:
            next_month_start = date(today.year, today.month + 1, 1)
        month_end = next_month_start - timedelta(days=1)

        stats = get_summary_stats(
            demo_user["id"],
            date_from=month_start.isoformat(),
            date_to=month_end.isoformat(),
        )
        assert stats["total_spent"] == pytest.approx(219.89), (
            "All 8 seeded expenses fall within the current month"
        )
        assert stats["transaction_count"] == 8

    def test_narrow_range_matching_one_expense(self, demo_user):
        today = date.today()
        y, m = today.year, today.month
        day2 = f"{y:04d}-{m:02d}-02"
        stats = get_summary_stats(demo_user["id"], date_from=day2, date_to=day2)
        assert stats["total_spent"] == pytest.approx(35.50)
        assert stats["transaction_count"] == 1
        assert stats["top_category"] == "Food"

    def test_range_with_no_matching_expenses_returns_zero_state(self, demo_user):
        # Far in the past — no seeded expense should fall here.
        stats = get_summary_stats(
            demo_user["id"], date_from="2000-01-01", date_to="2000-01-31"
        )
        assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    def test_lone_date_from_without_date_to_is_treated_as_unfiltered(self, demo_user):
        today = date.today()
        y, m = today.year, today.month
        stats = get_summary_stats(demo_user["id"], date_from=f"{y:04d}-{m:02d}-02")
        assert stats["transaction_count"] == 8, (
            "A single bound without the other must not filter (only applies "
            "when both bounds are given per spec)"
        )

    def test_lone_date_to_without_date_from_is_treated_as_unfiltered(self, demo_user):
        today = date.today()
        y, m = today.year, today.month
        stats = get_summary_stats(demo_user["id"], date_to=f"{y:04d}-{m:02d}-02")
        assert stats["transaction_count"] == 8

    def test_empty_user_with_date_range_returns_zero_state(self, empty_user):
        stats = get_summary_stats(
            empty_user, date_from="2020-01-01", date_to="2020-12-31"
        )
        assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


# --------------------------------------------------------------------- #
# Query helper: get_recent_transactions date filtering                  #
# --------------------------------------------------------------------- #

class TestGetRecentTransactionsDateFilter:
    def test_no_date_args_matches_unfiltered(self, demo_user):
        result = get_recent_transactions(demo_user["id"])
        assert len(result) == 8

    def test_range_restricts_to_expenses_within_bounds(self, demo_user):
        today = date.today()
        y, m = today.year, today.month
        result = get_recent_transactions(
            demo_user["id"],
            date_from=f"{y:04d}-{m:02d}-01",
            date_to=f"{y:04d}-{m:02d}-10",
        )
        # Days 2, 4, 6, 9 fall in [01, 10]
        assert len(result) == 4
        descriptions = {tx["description"] for tx in result}
        assert descriptions == {"Groceries", "Bus pass", "Electricity bill", "Pharmacy"}

    def test_range_ordering_and_limit_unaffected_by_filter(self, demo_user):
        today = date.today()
        y, m = today.year, today.month
        result = get_recent_transactions(
            demo_user["id"], limit=2,
            date_from=f"{y:04d}-{m:02d}-01",
            date_to=f"{y:04d}-{m:02d}-31",
        )
        assert len(result) == 2, "limit must still apply when a filter is active"
        dates = [tx["date"] for tx in result]
        assert dates == sorted(dates, reverse=True), "must remain most-recent-first"

    def test_range_with_no_matching_expenses_returns_empty_list(self, demo_user):
        result = get_recent_transactions(
            demo_user["id"], date_from="2000-01-01", date_to="2000-01-31"
        )
        assert result == []

    def test_empty_user_with_date_range_returns_empty_list(self, empty_user):
        assert get_recent_transactions(
            empty_user, date_from="2020-01-01", date_to="2020-12-31"
        ) == []


# --------------------------------------------------------------------- #
# Query helper: get_category_breakdown date filtering                   #
# --------------------------------------------------------------------- #

class TestGetCategoryBreakdownDateFilter:
    def test_no_date_args_matches_unfiltered(self, demo_user):
        result = get_category_breakdown(demo_user["id"])
        assert len(result) == 7
        assert sum(c["pct"] for c in result) == 100

    def test_range_restricts_categories_and_recalculates_percentages(self, demo_user):
        today = date.today()
        y, m = today.year, today.month
        day2 = f"{y:04d}-{m:02d}-02"
        result = get_category_breakdown(demo_user["id"], date_from=day2, date_to=day2)
        assert len(result) == 1
        assert result[0]["name"] == "Food"
        assert result[0]["amount"] == pytest.approx(35.50)
        assert result[0]["pct"] == 100, "percentages must be recalculated for the filtered range"

    def test_range_with_no_matching_expenses_returns_empty_list(self, demo_user):
        result = get_category_breakdown(
            demo_user["id"], date_from="2000-01-01", date_to="2000-01-31"
        )
        assert result == []

    def test_empty_user_with_date_range_returns_empty_list(self, empty_user):
        assert get_category_breakdown(
            empty_user, date_from="2020-01-01", date_to="2020-12-31"
        ) == []


# --------------------------------------------------------------------- #
# /profile route — custom valid range                                   #
# --------------------------------------------------------------------- #

class TestProfileCustomRangeRoute:
    def test_valid_custom_range_filters_all_three_sections(self, client, demo_user):
        login(client, demo_user["id"])
        today = date.today()
        y, m = today.year, today.month
        response = client.get(
            profile_url(f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-10")
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)

        # Only the 4 in-range expenses should appear.
        for description in ["Groceries", "Bus pass", "Electricity bill", "Pharmacy"]:
            assert description in body, f"Expected {description} within the filtered range"
        for description in ["Movie ticket", "New shoes", "Miscellaneous", "Restaurant"]:
            assert description not in body, f"Did not expect {description} outside the filtered range"

        # 35.50 + 15.00 + 60.00 + 20.00 = 130.50
        assert "₹130.50" in body, "Total spent must reflect only the filtered expenses"

    def test_valid_custom_range_still_shows_rupee_symbol(self, client, demo_user):
        login(client, demo_user["id"])
        today = date.today()
        y, m = today.year, today.month
        response = client.get(
            profile_url(f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-10")
        )
        body = response.get_data(as_text=True)
        assert "₹" in body, "₹ symbol must be present regardless of active filter"

    def test_range_with_no_expenses_shows_zero_state_no_errors(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get(profile_url("2000-01-01", "2000-01-31"))
        assert response.status_code == 200, "Empty-range result must not error"
        body = response.get_data(as_text=True)
        assert "₹0.00" in body, "Zero total spent must be shown"
        assert "—" in body, "Top category placeholder must be shown when no expenses match"
        for description in [
            "Groceries", "Bus pass", "Electricity bill", "Pharmacy",
            "Movie ticket", "New shoes", "Miscellaneous", "Restaurant",
        ]:
            assert description not in body, "No transactions should render for an empty range"


# --------------------------------------------------------------------- #
# /profile route — malformed / partial params fall back silently        #
# --------------------------------------------------------------------- #

class TestProfileMalformedParams:
    def test_malformed_date_from_falls_back_to_unfiltered(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get(profile_url("not-a-date", "2026-12-31"))
        assert response.status_code == 200, "Malformed date must not crash the app"
        body = response.get_data(as_text=True)
        assert "₹219.89" in body, "Malformed date_from must fall back to unfiltered totals"

    def test_malformed_date_to_falls_back_to_unfiltered(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get(profile_url("2026-01-01", "also-bad"))
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "₹219.89" in body

    def test_both_dates_malformed_falls_back_to_unfiltered(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get(profile_url("bogus", "garbage"))
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "₹219.89" in body

    def test_only_date_from_provided_falls_back_to_unfiltered(self, client, demo_user):
        login(client, demo_user["id"])
        today = date.today()
        y, m = today.year, today.month
        response = client.get(profile_url(date_from=f"{y:04d}-{m:02d}-02"))
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "₹219.89" in body, "A lone date_from without date_to must not filter"

    def test_only_date_to_provided_falls_back_to_unfiltered(self, client, demo_user):
        login(client, demo_user["id"])
        today = date.today()
        y, m = today.year, today.month
        response = client.get(profile_url(date_to=f"{y:04d}-{m:02d}-02"))
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "₹219.89" in body, "A lone date_to without date_from must not filter"


# --------------------------------------------------------------------- #
# /profile route — date_from > date_to                                  #
# --------------------------------------------------------------------- #

class TestProfileSwappedRange:
    def test_swapped_range_falls_back_to_unfiltered(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get(profile_url("2026-12-31", "2026-01-01"))
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "₹219.89" in body, "date_from > date_to must fall back to the unfiltered view"

    def test_swapped_range_shows_flash_error_message(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get(profile_url("2026-12-31", "2026-01-01"))
        body = response.get_data(as_text=True)
        assert "Start date must be before end date." in body, (
            "Expected the mandated flash error message text"
        )

    def test_equal_dates_are_not_treated_as_swapped(self, client, demo_user):
        # date_from == date_to is a valid single-day range, not swapped.
        login(client, demo_user["id"])
        today = date.today()
        y, m = today.year, today.month
        day2 = f"{y:04d}-{m:02d}-02"
        response = client.get(profile_url(day2, day2))
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Start date must be before end date." not in body
        assert "₹35.50" in body, "Single-day equal range should filter to that day's expense"


# --------------------------------------------------------------------- #
# Filter bar presets                                                    #
# --------------------------------------------------------------------- #

class TestFilterBarPresets:
    def test_default_view_shows_all_four_preset_labels(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        for label in ["This Month", "Last 3 Months", "Last 6 Months", "All Time"]:
            assert label in body, f"Expected preset label '{label}' in filter bar"

    def test_default_view_has_active_indicator_for_all_time(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert "active" in body, (
            "Expected some 'active' class/indicator to mark the currently applied filter"
        )

    def test_all_time_preset_link_has_no_query_params(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        # The "All Time" preset must be a clean /profile link with no query string.
        assert 'href="/profile"' in body, (
            "All Time preset must link to a bare /profile URL with no query params"
        )

    def test_this_month_preset_link_present_with_query_params(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert "/profile?" in body, (
            "Non-'All Time' presets must include date_from/date_to query params in their links"
        )
        assert "date_from=" in body
        assert "date_to=" in body

    def test_custom_range_form_fields_present(self, client, demo_user):
        login(client, demo_user["id"])
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert 'name="date_from"' in body
        assert 'name="date_to"' in body
        assert 'type="date"' in body

    def test_filtering_by_this_month_range_matches_full_month_preset(self, client, demo_user):
        # Applying the exact "This Month" range should include all seeded
        # expenses (they're all dated within the current month).
        login(client, demo_user["id"])
        today = date.today()
        month_start = today.replace(day=1)
        if today.month == 12:
            next_month_start = date(today.year + 1, 1, 1)
        else:
            next_month_start = date(today.year, today.month + 1, 1)
        month_end = next_month_start - timedelta(days=1)

        response = client.get(
            profile_url(month_start.isoformat(), month_end.isoformat())
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "₹219.89" in body, "This Month range should include all seeded expenses"
