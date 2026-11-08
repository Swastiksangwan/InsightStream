"""Safety gates must fail before application imports or database writes."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.core import database_safety as safety
from scripts import database_snapshot
from scripts.local_database import test_environment as read_test_environment


FIXTURE_URL = "postgresql://insightstream_test_runner:fixture-only@127.0.0.1/insightstream_test"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("changes", [
    {"INSIGHTSTREAM_ENV": "development"},
    {"INSIGHTSTREAM_ENV": "production"},
    {"INSIGHTSTREAM_ENV": ""},
    {"TEST_DATABASE_URL": ""},
    {"TEST_DATABASE_URL": "not a URL"},
    {"TEST_DATABASE_URL": "sqlite:///insightstream_test"},
    {"TEST_DATABASE_URL": FIXTURE_URL.replace("127.0.0.1", "example.invalid")},
    {"TEST_DATABASE_URL": FIXTURE_URL.replace("/insightstream_test", "/insightstream_db")},
    {"TEST_DATABASE_URL": FIXTURE_URL.replace("/insightstream_test", "/unknown")},
    {"TEST_DATABASE_URL": FIXTURE_URL.replace("/insightstream_test", "/insightstream_migrate_123456abcdef")},
    {"TEST_DATABASE_URL": FIXTURE_URL.replace("/insightstream_test", "")},
    {"TEST_DATABASE_URL": FIXTURE_URL.replace("insightstream_test_runner:", "postgres:")},
    {"TEST_DATABASE_URL": FIXTURE_URL + "?host=example.invalid"},
    {"TEST_DATABASE_URL": FIXTURE_URL.replace(":fixture-only", "")},
])
def test_unsafe_test_configuration_is_rejected_without_echoing_url(changes):
    environment = {"INSIGHTSTREAM_ENV": "test", "TEST_DATABASE_URL": FIXTURE_URL, **changes}
    with pytest.raises(safety.DatabaseSafetyError) as caught:
        safety.test_database_url(environment)
    assert "fixture-only" not in str(caught.value)
    assert "postgresql://" not in str(caught.value)


def test_missing_test_url_never_falls_back_to_database_url():
    with pytest.raises(safety.DatabaseSafetyError, match="no development fallback"):
        safety.test_database_url({"INSIGHTSTREAM_ENV": "test", "DATABASE_URL": FIXTURE_URL})


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_explicit_local_test_configuration_is_accepted(host):
    host = "[::1]" if host == "::1" else host
    raw = FIXTURE_URL.replace("127.0.0.1", host)
    assert safety.test_database_url({"INSIGHTSTREAM_ENV": "test", "TEST_DATABASE_URL": raw}) == raw


class IdentityConnection:
    def __init__(self, **changes):
        values = dict(database=safety.TEST_DATABASE, role=safety.TEST_ROLE, host="127.0.0.1/32",
            superuser=False, createdb=False, createrole=False, replication=False,
            bypassrls=False, owner=safety.TEST_ROLE,
            marker=json.dumps({"purpose": safety.TEST_MARKER}), membership=False)
        values.update(changes)
        self.row = tuple(values.values())

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, statement):
        assert statement.strip().startswith("SELECT")

    def fetchone(self):
        return self.row


@pytest.mark.parametrize("changes", [
    {"database": "insightstream_db"}, {"role": "postgres"},
    {"host": "203.0.113.1/32"}, {"superuser": True}, {"createdb": True},
    {"createrole": True}, {"replication": True}, {"bypassrls": True},
    {"owner": "postgres"}, {"marker": None}, {"marker": "not JSON"},
    {"marker": "{}"}, {"marker": "[]"}, {"marker": "null"}, {"membership": True},
])
def test_actual_connection_identity_and_privileges_are_verified(changes):
    with pytest.raises(safety.DatabaseSafetyError):
        safety.verify_test_connection(IdentityConnection(**changes))


def test_valid_actual_connection_has_only_sanitized_identity():
    result = safety.verify_test_connection(IdentityConnection())
    assert result["database"] == safety.TEST_DATABASE
    assert result["role"] == safety.TEST_ROLE
    assert "password" not in result


@pytest.mark.parametrize("mode,url", [
    ("test", ""),
    ("test", FIXTURE_URL.replace("/insightstream_test", "/insightstream_db")),
    ("unit-test", ""),
])
def test_configuration_rejects_unsafe_engine_initialization_in_subprocess(mode, url):
    environment = os.environ.copy()
    environment.update(INSIGHTSTREAM_ENV=mode, TEST_DATABASE_URL=url, DATABASE_URL=FIXTURE_URL)
    environment["PYTHONPATH"] = str(REPO_ROOT / "backend")
    script = """
import sys
try:
    import app.core.config
except RuntimeError:
    assert 'app.db.session' not in sys.modules
    raise SystemExit(0)
raise SystemExit(1)
"""
    result = subprocess.run([sys.executable, "-B", "-c", script], env=environment,
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "fixture-only" not in result.stdout + result.stderr


def test_backup_refuses_repository_destination_before_connecting():
    with pytest.raises(RuntimeError, match="outside the Git repository"):
        database_snapshot.backup(FIXTURE_URL, REPO_ROOT / "backups")


def test_restore_refuses_tampered_archive_before_connecting(tmp_path):
    archive = tmp_path / "backup.dump"
    archive.write_bytes(b"not a database archive")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"backup_path": str(archive), "sha256": "wrong"}))
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        database_snapshot.restore_verify(FIXTURE_URL, manifest)


def test_constraint_normalization_preserves_actual_check_semantics():
    original = "CHECK (kind = ANY ((ARRAY['a'::character varying, 'b'::character varying])::text[]))"
    restored = "CHECK (kind = ANY (ARRAY[('a'::character varying)::text, ('b'::character varying)::text]))"
    assert database_snapshot.canonical_constraint(original) == restored
    assert database_snapshot.canonical_constraint(original.replace("'b'", "'c'")) != restored
    assert database_snapshot.canonical_constraint("CHECK (score <= 100)") == "CHECK (score <= 100)"


def test_private_environment_permissions_are_enforced(tmp_path):
    environment = tmp_path / "test.env"
    environment.write_text("INSIGHTSTREAM_ENV=test\n")
    environment.chmod(0o644)
    with pytest.raises(safety.DatabaseSafetyError, match="0600"):
        read_test_environment(environment)


def test_database_urls_are_redacted_in_failure_output():
    rendered = safety.redact_database_urls("Failed connecting to " + FIXTURE_URL + " in a fixture")
    assert "fixture-only" not in rendered
    assert "postgresql://" not in rendered
    assert "[database URL redacted]" in rendered
