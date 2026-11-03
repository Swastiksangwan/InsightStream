import os
from pathlib import Path

from dotenv import load_dotenv

from sqlalchemy.engine import make_url

from app.core.database_safety import DatabaseSafetyError, TEST_DATABASE, TEST_ROLE, test_database_url


def configured_database_url():
    mode = os.getenv("INSIGHTSTREAM_ENV", "development")
    if mode == "test":
        # Never discover development .env values in a test process.
        return test_database_url(os.environ)
    if mode == "unit-test":
        raise DatabaseSafetyError("Unit-only tests must not initialize an application database engine.")
    if mode not in {"development", "production"}:
        raise DatabaseSafetyError("Unknown INSIGHTSTREAM_ENV; database initialization refused.")
    # Explicit location and override=False preserve exported-variable precedence.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    raw_url = os.getenv("DATABASE_URL")
    if raw_url:
        target = make_url(raw_url)
        if target.database == TEST_DATABASE or target.username == TEST_ROLE:
            raise DatabaseSafetyError("The disposable test target requires INSIGHTSTREAM_ENV=test.")
    return raw_url


DATABASE_URL = configured_database_url()
