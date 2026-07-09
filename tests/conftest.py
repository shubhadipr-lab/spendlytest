import pytest
from werkzeug.security import generate_password_hash

import database.db as db


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_expense_tracker.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    yield


@pytest.fixture
def demo_user(temp_db):
    db.seed_db()
    row = db.get_user_by_email("demo@spendly.com")
    return dict(row)


@pytest.fixture
def empty_user(temp_db):
    user_id = db.create_user(
        "New User", "new.user@example.com", generate_password_hash("password123")
    )
    return user_id


@pytest.fixture
def client():
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client
