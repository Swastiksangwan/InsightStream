"""Fail-closed rules for the disposable local PostgreSQL test database.

This module deliberately does not load dotenv files or import application engines.
"""

import ipaddress
import json
import re
from collections.abc import Mapping

import psycopg2
from sqlalchemy.engine import make_url


TEST_DATABASE = "insightstream_test"
TEST_ROLE = "insightstream_test_runner"
TEST_MARKER = "insightstream-disposable-test-v1"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class DatabaseSafetyError(RuntimeError):
    """A target could not be proved safe; never include a DSN in this error."""


def test_database_url(environment: Mapping[str, str]) -> str:
    if environment.get("INSIGHTSTREAM_ENV") != "test":
        raise DatabaseSafetyError("INSIGHTSTREAM_ENV=test is required for database tests.")
    raw = environment.get("TEST_DATABASE_URL")
    if not raw:
        raise DatabaseSafetyError("TEST_DATABASE_URL is required; no development fallback is allowed.")
    try:
        url = make_url(raw)
    except Exception:
        raise DatabaseSafetyError("TEST_DATABASE_URL is not a valid PostgreSQL URL.") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg2"}:
        raise DatabaseSafetyError("Tests require the local PostgreSQL installation.")
    if url.host not in LOCAL_HOSTS or url.query:
        raise DatabaseSafetyError("Test connections require an explicit loopback host and no URL options.")
    if url.database != TEST_DATABASE or url.username != TEST_ROLE:
        raise DatabaseSafetyError(
            f"Only database {TEST_DATABASE} with role {TEST_ROLE} is permitted."
        )
    if not url.password:
        raise DatabaseSafetyError("An explicit dedicated test-role password is required.")
    return url.render_as_string(hide_password=False)


def connection_parameters(raw_url: str) -> dict:
    url = make_url(raw_url)
    return {
        "host": url.host,
        "port": url.port or 5432,
        "user": url.username,
        "password": url.password,
        "dbname": url.database,
        "connect_timeout": 8,
    }


def redact_database_urls(value: str) -> str:
    """Keep failed-test tracebacks/captured logs from printing connection URLs."""
    return re.sub(r"postgres(?:ql)?(?:\+[\w]+)?://[^\s'\"<>]+", "[database URL redacted]", value)


def verify_test_connection(connection) -> dict:
    """Inspect actual server identity before any fixture or application write.

    The caller owns this connection. Only SELECTs are issued. No password, user
    records or connection URL is returned, including on failure.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_database(), current_user, inet_server_addr()::text,
                   r.rolsuper, r.rolcreatedb, r.rolcreaterole,
                   r.rolreplication, r.rolbypassrls,
                   pg_get_userbyid(d.datdba),
                   shobj_description(d.oid, 'pg_database'),
                   EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
            FROM pg_roles r JOIN pg_database d ON d.datname=current_database()
            WHERE r.rolname=current_user
            """
        )
        row = cursor.fetchone()
    if not row or row[0] != TEST_DATABASE or row[1] != TEST_ROLE:
        raise DatabaseSafetyError("Connected database/role does not match the disposable test target.")
    try:
        local = ipaddress.ip_address((row[2] or "").split("/")[0]).is_loopback
        marker = json.loads(row[9] or "{}")
    except (ValueError, TypeError):
        raise DatabaseSafetyError("Test server address or ownership marker is invalid.") from None
    if not local or any(row[3:8]) or row[10]:
        raise DatabaseSafetyError("Test role must be local, unprivileged and have no role memberships.")
    if row[8] != TEST_ROLE or not isinstance(marker, dict) or marker.get("purpose") != TEST_MARKER:
        raise DatabaseSafetyError("Test database ownership/marker is missing; run prepare-test safely.")
    return {"database": row[0], "role": row[1], "marker": marker}


def verify_test_target(raw_url: str) -> dict:
    try:
        connection = psycopg2.connect(**connection_parameters(raw_url))
        try:
            connection.set_session(readonly=True)
            return verify_test_connection(connection)
        finally:
            connection.rollback()
            connection.close()
    except DatabaseSafetyError:
        raise
    except Exception:
        raise DatabaseSafetyError("Cannot verify the local test database; no tests were started.") from None
