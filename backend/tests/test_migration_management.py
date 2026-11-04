"""Real disposable-PostgreSQL lifecycle plus pure fail-closed contract checks."""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.database_safety import DatabaseSafetyError
from scripts.database_snapshot import compare_snapshots, connect, snapshot
from scripts import migration_management as manager
from scripts import migration_database
from scripts.migration_database import read_check_targets, target_url, verify_url
from scripts.migration_schema import schema_signature


@pytest.fixture
def migration_repository(tmp_path):
    for filename in ("schema.sql", "indexes.sql"):
        shutil.copyfile(manager.ROOT / filename, tmp_path / filename)
    shutil.copytree(manager.ROOT / "migrations", tmp_path / "migrations",
        ignore=lambda directory, names: [name for name in names if
            directory.endswith("/managed") and name.endswith(".sql")])
    return tmp_path


def write_migration(root, name, sql):
    path = root / "migrations/managed" / name
    path.write_text(manager.HEADER + "\n" + sql + "\n")
    return path


@pytest.mark.parametrize("sql", [
    "COMMIT;", "BEGIN;", "VACUUM;", "REINDEX TABLE public.content;",
    "CREATE INDEX CONCURRENTLY unsafe ON public.content(title);",
    "CREATE DATABASE unsafe;", "ALTER SYSTEM SET work_mem='1MB';",
    "CREATE ROLE unsafe;", "SET search_path=evil;", "COPY content TO PROGRAM 'echo unsafe';",
    "DO $$ BEGIN NULL; END $$;", "CALL unsafe();", "SELECT pg_advisory_unlock_all();",
    "CREATE TABLE unsafe AS SELECT 1;", "INSERT INTO content(title) VALUES ('unsafe');",
    "CREATE TEMP TABLE unsafe(id integer);", "DROP TABLE public.content;",
    "ALTER TABLE insightstream_migrations.history ADD COLUMN unsafe integer;",
    'ALTER TABLE "insightstream_migrations".history ADD COLUMN unsafe integer;',
    "ALTER TABLE content ADD COLUMN x text DEFAULT E'\\123';",
    "ALTER TABLE content ADD COLUMN x integer", "/* unterminated",
    "CREATE TABLE unsafe(value text DEFAULT 'unterminated);",
])
def test_unsupported_or_nontransactional_sql_fails_closed(sql):
    with pytest.raises(manager.MigrationError):
        manager.transactional_statements(manager.HEADER + "\n" + sql)


def test_statement_scanner_handles_literals_semicolons_and_nested_comments():
    source = manager.HEADER + "\n/* outer /* inner */ comment */\n" + (
        "CREATE TABLE public.fixture(id integer, note text DEFAULT 'it''s; safe');\n"
        "-- misleading COMMIT; is only a comment\n"
        "CREATE UNIQUE INDEX fixture_id ON public.fixture(id);\n")
    assert len(manager.transactional_statements(source)) == 2


@pytest.mark.parametrize("sql", [
    # Validation only: these statements must never reach PostgreSQL.
    "ALTER TABLE pg_catalog.pg_class ADD COLUMN dangerous integer;",
    "CREATE INDEX dangerous ON pg_catalog.pg_class(oid);",
    "DROP INDEX pg_catalog.pg_class_oid_index;",
    'ALTER TABLE "pg_catalog"."pg_class" ADD COLUMN dangerous integer;',
    'CREATE INDEX "dangerous" ON "pg_catalog"."pg_class"(oid);',
    'DROP INDEX "pg_catalog"."pg_class_oid_index";',
    "ALTER TABLE information_schema.tables ADD COLUMN dangerous integer;",
    "CREATE TABLE pg_temp.fixture(id integer);",
    "CREATE TABLE pg_temp_123.fixture(id integer);",
    "CREATE TABLE pg_toast.fixture(id integer);",
    "CREATE INDEX dangerous ON insightstream_migrations.history(version);",
    "DROP INDEX insightstream_migrations.history_pkey;",
    "ALTER TABLE pg_class ADD COLUMN dangerous integer;",
    "CREATE INDEX dangerous ON pg_class(oid);",
    "DROP INDEX pg_class_oid_index;",
    # Even known names must not resolve through search_path or a temporary table.
    "ALTER TABLE content ADD COLUMN note text;",
    "CREATE INDEX content_note ON content(title);",
    "DROP INDEX idx_content_title_lower;",
    "ALTER TABLE public.unknown_table ADD COLUMN note text;",
    "CREATE INDEX unknown_note ON public.unknown_table(title);",
    "DROP INDEX public.unknown_index;",
    'ALTER TABLE "PUBLIC".content ADD COLUMN note text;',
    'ALTER TABLE public."Content" ADD COLUMN note text;',
    'ALTER TABLE "public.content" ADD COLUMN note text;',
    "ALTER TABLE public.pg_class ADD COLUMN note text;",
    "CREATE TABLE public.pg_internal(id integer);",
    "CREATE TABLE public.sql_internal(id integer);",
    'CREATE TABLE public.""(id integer);',
    'CREATE TABLE public."' + 'a' * 64 + '"(id integer);',
    'CREATE TABLE public."' + 'é' * 32 + '"(id integer);',
    'CREATE TABLE public."bad\nname"(id integer);',
    "ALTER TABLE public.content SET SCHEMA pg_catalog;",
    "ALTER TABLE public.content RENAME TO pg_class;",
    "ALTER TABLE public.content INHERIT pg_catalog.pg_class;",
    "CREATE TABLE public.fixture(LIKE pg_catalog.pg_class);",
    "CREATE TABLE public.fixture(id integer) INHERITS (pg_catalog.pg_class);",
    "CREATE TABLE public.fixture(id integer) PARTITION BY RANGE(id);",
    "ALTER TABLE public.content ADD COLUMN parent oid REFERENCES pg_catalog.pg_class(oid);",
    "ALTER TABLE public.content ADD COLUMN parent integer REFERENCES content(id);",
    "ALTER TABLE public.content ADD COLUMN parent integer REFERENCES public.unknown_table(id);",
    "ALTER TABLE public.content ADD CONSTRAINT fixture UNIQUE USING INDEX pg_catalog.pg_class_oid_index;",
    "DROP INDEX public.idx_content_title_lower, pg_catalog.pg_class_oid_index;",
    "DROP INDEX public.idx_content_title_lower CASCADE;",
    "CREATE INDEX public.fixture ON public.content(title);",
    "ALTER TABLE public.content DROP COLUMN title CASCADE;",
])
def test_unsafe_ambiguous_or_unapproved_ddl_targets_are_rejected_without_execution(sql):
    with pytest.raises(manager.MigrationError):
        manager.transactional_statements(manager.HEADER + "\n" + sql)


@pytest.mark.parametrize("sql", [
    "ALTER TABLE public.content ADD COLUMN note text;",
    'ALTER TABLE "public"."content" ADD COLUMN "Note" text;',
    "ALTER TABLE PUBLIC.CONTENT ADD COLUMN note text;",
    "ALTER TABLE IF EXISTS ONLY public.content ADD COLUMN note text;",
    "CREATE INDEX content_note ON public.content(title);",
    'CREATE UNIQUE INDEX "Content Note" ON "public"."content"(title);',
    "CREATE INDEX IF NOT EXISTS content_note ON ONLY public.content USING btree(title);",
    "DROP INDEX public.idx_content_title_lower;",
    'DROP INDEX IF EXISTS "public"."idx_content_title_lower" RESTRICT;',
    "ALTER TABLE public.content ADD COLUMN parent integer REFERENCES public.content(id);",
    'CREATE TABLE public."Review Fixture"("id" integer, "a""b" text);'
    'ALTER TABLE public."Review Fixture" ADD COLUMN note text;'
    'CREATE INDEX "Quoted ""Index" ON public."Review Fixture"("a""b");'
    'DROP INDEX public."Quoted ""Index";',
    "CREATE TABLE public.fixture(id integer REFERENCES public.fixture(id));",
])
def test_explicit_public_application_ddl_and_ordinary_quotes_are_supported(sql):
    assert manager.transactional_statements(manager.HEADER + "\n" + sql)


def test_approved_objects_follow_migration_order(migration_repository):
    write_migration(migration_repository, "016_table.sql", "CREATE TABLE public.fixture(id integer);")
    write_migration(migration_repository, "017_index.sql", "CREATE INDEX fixture_id ON public.fixture(id);")
    write_migration(migration_repository, "018_drop.sql", "DROP INDEX public.fixture_id;")
    assert [item.version for item in manager.repository_state(migration_repository)[2]] == [16, 17, 18]
    write_migration(migration_repository, "016_table.sql", "ALTER TABLE public.fixture ADD COLUMN note text;")
    with pytest.raises(manager.MigrationError, match="approved application table"):
        manager.repository_state(migration_repository)


def test_invalid_file_does_not_approve_its_new_objects():
    tables, indexes = manager.application_objects()
    original = tables.copy(), indexes.copy()
    with pytest.raises(manager.MigrationError):
        manager.transactional_statements(manager.HEADER + "\n"
            "CREATE TABLE public.fixture(id integer);"
            "CREATE INDEX fixture_id ON public.fixture(id);"
            "ALTER TABLE pg_catalog.pg_class ADD COLUMN dangerous integer;",
            approved_tables=tables, approved_indexes=indexes)
    assert (tables, indexes) == original


@pytest.mark.parametrize("filenames", [
    ["017_gap.sql"], ["016_first.sql", "018_gap.sql"],
    ["016_first.sql", "016_duplicate.sql"], ["015_legacy.sql"], ["016_BAD.sql"],
])
def test_missing_duplicate_out_of_order_versions_are_rejected(migration_repository, filenames):
    for name in filenames:
        write_migration(migration_repository, name, "CREATE INDEX fixture ON public.content(title);")
    with pytest.raises(manager.MigrationError):
        manager.repository_state(migration_repository)


@pytest.mark.parametrize("filename", ["schema.sql", "indexes.sql", "migrations/ledger.sql",
                                    "migrations/014_add_content_video_metadata.sql"])
def test_immutable_baseline_and_historical_sources_are_checked(migration_repository, filename):
    with (migration_repository / filename).open("a") as handle:
        handle.write("\n-- changed\n")
    with pytest.raises(manager.MigrationError, match="checksum"):
        manager.repository_state(migration_repository)


def test_new_sql_in_historical_directory_is_not_implicitly_applied(migration_repository):
    (migration_repository / "migrations/016_wrong_location.sql").write_text("SELECT 1;")
    with pytest.raises(manager.MigrationError, match="historical"):
        manager.repository_state(migration_repository)


@pytest.mark.parametrize("target", ["postgres", "production", "insightstream_verify_unknown", "unknown"])
def test_unknown_targets_are_rejected_without_connecting(target):
    with pytest.raises(DatabaseSafetyError, match="Unknown"):
        target_url(target)


def test_development_target_is_forbidden_in_test_process(monkeypatch):
    monkeypatch.setenv("INSIGHTSTREAM_ENV", "test")
    with pytest.raises(DatabaseSafetyError, match="cannot select"):
        target_url("insightstream_db")
    with pytest.raises(manager.MigrationError, match="approve-development"):
        manager.execute(None, "insightstream_db", "baseline", "insightstream_db", "live")
    with pytest.raises(manager.MigrationError, match="confirm-target"):
        manager.execute(None, "insightstream_db", "baseline", "other", "live")


def test_historical_replay_flag_is_rejected_before_database_access():
    result = subprocess.run([sys.executable, "-B", str(manager.ROOT / "scripts/run_tests.py"),
        "--unit-only", "--run-migration-tests", "--collect-only", "-q"],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 4
    assert "Historical replay" in result.stderr


def test_unit_runner_discovers_nested_options_with_external_migration_path(tmp_path):
    result = subprocess.run([sys.executable, "-B", str(manager.ROOT / "scripts/run_tests.py"),
        "--unit-only", "--migration-env", str(tmp_path / "not-needed.json"), "--collect-only", "-q"],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0
    assert "deselected" in result.stdout


def test_forged_migration_test_config_cannot_select_development(tmp_path):
    path = tmp_path / "targets.json"
    item = {"database": "insightstream_db", "url": "not needed"}
    path.write_text(json.dumps({key: item for key in ("fresh", "existing", "historical")}))
    path.chmod(0o600)
    with pytest.raises(DatabaseSafetyError, match="Cannot validate"):
        read_check_targets(path)


def test_reading_migration_configuration_verifies_but_does_not_consume_it(tmp_path, monkeypatch):
    from unittest.mock import Mock

    path = tmp_path / "targets.json"
    targets = {key: {"database": "insightstream_migrate_" + str(number) * 12,
                     "url": "not a credential"}
               for number, key in enumerate(("fresh", "existing", "historical"), start=1)}
    path.write_text(json.dumps(targets))
    path.chmod(0o600)
    original = path.read_bytes()
    connections = [Mock() for _ in range(6)]
    connect_mock = Mock(side_effect=connections)
    verify_mock = Mock()
    monkeypatch.setattr(migration_database, "connect", connect_mock)
    monkeypatch.setattr(migration_database, "verify_url", Mock())
    monkeypatch.setattr(migration_database, "verify_target", verify_mock)
    assert read_check_targets(path) == targets
    assert read_check_targets(path) == targets
    assert path.read_bytes() == original
    assert verify_mock.call_count == 6
    for connection in connections:
        connection.set_session.assert_called_once_with(readonly=True)
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()


def test_migration_url_cannot_redirect_to_unknown_server_or_role():
    with pytest.raises(DatabaseSafetyError, match="explicit"):
        verify_url("postgresql://invalid@remote.invalid/insightstream_db", "insightstream_db")


def test_snapshot_comparison_includes_management_history_and_is_backward_compatible():
    state = {"tables": {}, "catalog": {}, "schema_sha256": "a",
             "schema_object_counts": {}, "sequences_sha256": "b"}
    assert all(compare_snapshots(state, {**state, "migration_management": None}).values())
    assert not compare_snapshots(state, {**state, "migration_management": {"history_sha256": "changed"}})["migration_management"]


def test_development_backup_is_required_before_any_connection():
    with pytest.raises(manager.MigrationError, match="backup-manifest"):
        manager.verify_development_backup(None)


@pytest.mark.parametrize("change", ["stale", "unverified", "tampered"])
def test_bad_development_backup_is_rejected_before_connecting(tmp_path, change):
    archive = tmp_path / "private.dump"
    archive.write_bytes(b"fixture archive, never a real dump")
    values = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "verified": True,
              "archive_readable": True, "comparisons": {"tables": True}, "source_database": "insightstream_db",
              "backup_path": str(archive), "sha256": manager.sha256(archive)}
    if change == "stale":
        values["created_at_utc"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    elif change == "unverified":
        values["verified"] = False
    else:
        values["sha256"] = "changed"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(values))
    path.chmod(0o600)
    with pytest.raises(manager.MigrationError, match="24 hours|checksum"):
        manager.verify_development_backup(path)


def test_running_suite_blocks_test_schema_migration_before_ddl(db_session):
    connection = connect(db_session.get_bind().url)
    try:
        with pytest.raises(manager.MigrationError, match="advisory lock"):
            manager.execute(connection, "insightstream_test", "baseline", "insightstream_test", "declarative")
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('insightstream_migrations.history')")
            assert cursor.fetchone()[0] is None
    finally:
        connection.rollback()
        connection.close()


def test_fresh_migration_lifecycle_is_transactional_and_preserves_data(migration_targets, migration_repository):
    """One new database follows a realistic lifecycle, without schema resets."""
    entry = migration_targets["fresh"]
    target = entry["database"]
    connection = connect(entry["url"])
    try:
        connection.autocommit = True  # The runner must restore transactional mode.
        result = manager.execute(connection, target, "initialize", target, root=migration_repository)
        assert result["baseline_profile"] == "declarative"
        assert result["applied_versions"] == []
        assert result["baseline_registered"] is True
        with connection.cursor() as cursor:
            cursor.execute("SELECT version,kind FROM insightstream_migrations.history")
            assert cursor.fetchall() == [(0, "baseline")]
            cursor.execute("INSERT INTO content(title,content_type) VALUES('Migration sentinel','movie')")
        connection.commit()
        assert manager.execute(connection, target, "baseline", target, "declarative", root=migration_repository)["executed_now"] == []

        path = write_migration(migration_repository, "016_fixture.sql",
            "CREATE TABLE public.migration_fixture(id integer PRIMARY KEY, value text);\n"
            "ALTER TABLE public.content ADD COLUMN migration_note text;")
        result = manager.execute(connection, target, "apply", target, root=migration_repository)
        assert result["executed_now"] == [16]
        assert manager.execute(connection, target, "apply", target, root=migration_repository)["executed_now"] == []
        with connection.cursor() as cursor:
            cursor.execute("SELECT title FROM content")
            assert cursor.fetchall() == [("Migration sentinel",)]
        connection.rollback()
        state = snapshot(connection)
        assert state["migration_management"]["rows"] == 2
        connection.rollback()

        original = path.read_text()
        path.write_text(original + "-- altered checksum\n")
        with pytest.raises(manager.MigrationError, match="checksum"):
            manager.execute(connection, target, "apply", target, root=migration_repository)
        path.unlink()
        with pytest.raises(manager.MigrationError, match="missing"):
            manager.inspect(connection, target, migration_repository)
        connection.rollback()
        path.write_text(original)

        # Entire pending batch rolls back, including the history entries.
        write_migration(migration_repository, "017_valid.sql",
            "CREATE INDEX fixture_value ON public.migration_fixture(value);")
        bad = write_migration(migration_repository, "018_failure.sql",
            "ALTER TABLE public.content ADD COLUMN must_rollback integer;\n"
            "CREATE INDEX impossible ON public.content(missing_column);")
        with pytest.raises(manager.MigrationError, match="rolled back"):
            manager.execute(connection, target, "apply", target, root=migration_repository)
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.fixture_value')")
            assert cursor.fetchone()[0] is None
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='content' AND column_name='must_rollback'")
            assert cursor.fetchone() is None
            cursor.execute("SELECT version FROM insightstream_migrations.history ORDER BY version")
            assert cursor.fetchall() == [(0,), (16,)]
        connection.rollback()
        bad.unlink()

        holder = connect(entry["url"])
        try:
            with holder.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (manager.MIGRATION_LOCK_KEY,))
            with pytest.raises(manager.MigrationError, match="advisory lock"):
                manager.execute(connection, target, "apply", target, root=migration_repository)
        finally:
            holder.rollback()
            holder.close()
        assert manager.execute(connection, target, "apply", target, root=migration_repository)["executed_now"] == [17]

        with connection.cursor() as cursor:
            cursor.execute("UPDATE insightstream_migrations.history SET version=19 WHERE version=17")
        with pytest.raises(manager.MigrationError, match="out of order"):
            manager.inspect(connection, target, migration_repository)
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE content ADD COLUMN unexpected_drift text")
        with pytest.raises(manager.MigrationError, match="drifted"):
            manager.inspect(connection, target, migration_repository)
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE insightstream_migrations.history ADD COLUMN unexpected integer")
        with pytest.raises(manager.MigrationError, match="structure"):
            manager.inspect(connection, target, migration_repository)
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("CREATE POLICY unexpected ON content USING (TRUE)")
        with pytest.raises(manager.MigrationError, match="drifted"):
            manager.inspect(connection, target, migration_repository)
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA pgevil")
        with pytest.raises(manager.MigrationError, match="schemas/extensions"):
            manager.inspect(connection, target, migration_repository)
        connection.rollback()
        assert manager.inspect(connection, target, migration_repository)["applied_versions"] == [16, 17]
    finally:
        connection.rollback()
        connection.close()


def test_existing_verified_baseline_does_not_replay_or_repair(migration_targets, migration_repository):
    entry = migration_targets["existing"]
    target = entry["database"]
    connection = connect(entry["url"])
    try:
        # Retain actual managed files when a future development source is already
        # migrated; only the runner lifecycle's synthetic SQL is isolated away.
        for path in (manager.ROOT / "migrations/managed").glob("*.sql"):
            shutil.copyfile(path, migration_repository / "migrations/managed" / path.name)
        before = schema_signature(connection)
        state = manager.inspect(connection, target, migration_repository)
        profile = state["baseline_profile"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            before_indexes = {row[0] for row in cursor.fetchall()}
        connection.rollback()
        wrong = "declarative" if profile == "live" else "live"
        with pytest.raises(manager.MigrationError, match="does not match"):
            manager.execute(connection, target, "baseline", target, wrong, root=migration_repository)
        adopted = manager.execute(connection, target, "baseline", target, profile, root=migration_repository)
        assert adopted["applied_versions"] == state["applied_versions"] and adopted["baseline_registered"]
        assert schema_signature(connection) == before
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM content")
            assert cursor.fetchone()[0] == 0  # schema-only clone, no private rows
            cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            indexes = {row[0] for row in cursor.fetchall()}
            assert indexes == before_indexes
            if not state["applied_versions"] and profile == "live":
                assert not set(state["known_baseline_differences"]["indexes_missing_from_live"]) & indexes
            cursor.execute("SELECT version,provenance FROM insightstream_migrations.history WHERE version=0")
            assert cursor.fetchall() == [(0, {"source_commit": "349c179073208fa01617d88d6368465c7dfc8216", "historical_execution": "not_asserted"})]
        manifest = migration_repository / "migrations/baseline.json"
        manifest.write_text(manifest.read_text() + "\n")
        with pytest.raises(manager.MigrationError, match="manifest/provenance"):
            manager.inspect(connection, target, migration_repository)
    finally:
        connection.rollback()
        connection.close()


def test_original_historical_assertions_execute_only_on_new_disposable_database(migration_targets, migration_repository):
    from test_content_video_endpoints import (
        test_video_hardening_migration_is_idempotent_and_schema_matches,
        test_video_hardening_migration_preserves_existing_rows,
    )

    entry = migration_targets["historical"]
    connection = connect(entry["url"])
    try:
        manager.execute(connection, entry["database"], "initialize", entry["database"], root=migration_repository)
    finally:
        connection.close()
    engine = create_engine(entry["url"])
    try:
        with Session(engine) as session:
            # Call the original functions without changing a single assertion.
            test_video_hardening_migration_is_idempotent_and_schema_matches(session)
            test_video_hardening_migration_preserves_existing_rows(session)
            assert session.execute(text("SELECT version FROM insightstream_migrations.history")).scalars().all() == [0]
        connection = connect(entry["url"])
        try:
            # 015 creates a second equivalent CHECK on the consolidated schema.
            with pytest.raises(manager.MigrationError, match="drifted"):
                manager.inspect(connection, entry["database"], migration_repository)
        finally:
            connection.rollback()
            connection.close()
    finally:
        engine.dispose()
