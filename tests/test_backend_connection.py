from datetime import datetime

import pytest

from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# --------------------------------------------------------------------- #
# get_user_by_id                                                        #
# --------------------------------------------------------------------- #

def test_get_user_by_id_demo_user(demo_user):
    result = get_user_by_id(demo_user["id"])
    assert result is not None
    assert result["name"] == "Demo User"
    assert result["email"] == "demo@spendly.com"
    assert result["member_since"] == datetime.now().strftime("%B %Y")


def test_get_user_by_id_nonexistent(demo_user):
    assert get_user_by_id(999999) is None


# --------------------------------------------------------------------- #
# get_summary_stats                                                     #
# --------------------------------------------------------------------- #

def test_get_summary_stats_demo_user(demo_user):
    stats = get_summary_stats(demo_user["id"])
    assert stats["total_spent"] == pytest.approx(219.89)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_empty_user(empty_user):
    stats = get_summary_stats(empty_user)
    assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


# --------------------------------------------------------------------- #
# get_recent_transactions                                               #
# --------------------------------------------------------------------- #

def test_get_recent_transactions_demo_user(demo_user):
    result = get_recent_transactions(demo_user["id"])
    assert len(result) == 8
    for tx in result:
        assert set(tx.keys()) == {"id", "date", "description", "category", "amount"}
        assert isinstance(tx["amount"], (int, float))
        assert not isinstance(tx["amount"], str)

    dates = [tx["date"] for tx in result]
    assert dates == sorted(dates, reverse=True)


def test_get_recent_transactions_demo_user_limit(demo_user):
    result = get_recent_transactions(demo_user["id"], limit=3)
    assert len(result) == 3


def test_get_recent_transactions_empty_user(empty_user):
    assert get_recent_transactions(empty_user) == []


# --------------------------------------------------------------------- #
# get_category_breakdown                                                #
# --------------------------------------------------------------------- #

def test_get_category_breakdown_demo_user(demo_user):
    result = get_category_breakdown(demo_user["id"])
    assert len(result) == 7
    assert sum(c["pct"] for c in result) == 100
    assert result[0]["name"] == "Bills"
    assert result[0]["amount"] == pytest.approx(60.0)


def test_get_category_breakdown_empty_user(empty_user):
    assert get_category_breakdown(empty_user) == []


# --------------------------------------------------------------------- #
# /profile route                                                        #
# --------------------------------------------------------------------- #

def test_profile_requires_login(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_demo_user(client, demo_user):
    with client.session_transaction() as sess:
        sess["user_id"] = demo_user["id"]

    response = client.get("/profile")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "₹219.89" in body
    assert "Bills" in body
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "Ananya Sharma" not in body
    assert "₹18,650" not in body


def test_profile_empty_user(client, empty_user):
    with client.session_transaction() as sess:
        sess["user_id"] = empty_user

    response = client.get("/profile")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "₹0.00" in body
    assert "—" in body
