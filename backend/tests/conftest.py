import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db.session import SessionLocal
from app.main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_user_id(db_session):
    row = db_session.execute(
        text("SELECT id FROM users WHERE email = :email;"),
        {"email": "test@example.com"},
    ).mappings().first()

    assert row is not None, "Expected seeded user test@example.com to exist."
    return row["id"]


@pytest.fixture
def content_id_by_title(db_session):
    def _get_content_id(title):
        row = db_session.execute(
            text("SELECT id FROM content WHERE title = :title;"),
            {"title": title},
        ).mappings().first()

        assert row is not None, f"Expected seeded content title {title!r} to exist."
        return row["id"]

    return _get_content_id
