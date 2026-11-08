"""Small, explicit, transactional migration ledger. Historical SQL is never replayed."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import psycopg2

from app.core.database_safety import DatabaseSafetyError
from scripts.database_snapshot import compare_snapshots, connect, snapshot
from scripts.migration_database import target_url, verify_target
from scripts.migration_schema import (
    MANAGEMENT_SCHEMA, environment_shape, schema_signature,
)
from scripts.test_support import TEST_LOCK_KEY


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_LOCK_KEY = 182736452
HEADER = "-- insightstream-migration: transactional"


class MigrationError(DatabaseSafetyError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    checksum: str
    statements: tuple[str, ...]


def application_objects(root=ROOT):
    """Explicit names from the checksum-pinned baseline, not search_path lookup."""
    tables = set(re.findall(r"(?m)^CREATE TABLE (?:IF NOT EXISTS )?(\w+)\s*\(",
                            (Path(root) / "schema.sql").read_text()))
    indexes = set(re.findall(r"(?m)^CREATE (?:UNIQUE )?INDEX (?:IF NOT EXISTS )?(\w+)\s",
                             (Path(root) / "indexes.sql").read_text()))
    return tables, indexes


def identifier(token):
    if re.fullmatch(r'"(?:[^"]|"")*"', token):
        name = token[1:-1].replace('""', '"')
    elif re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", token):
        name = token.lower()
    else:
        raise MigrationError("Expected an ordinary SQL identifier.")
    # PostgreSQL truncates identifiers at 63 bytes; never validate an alias.
    if not name or len(name.encode("utf-8")) > 63 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise MigrationError("Empty, control-character or truncated identifiers are unsupported.")
    return name


def object_name(tokens, position):
    if position >= len(tokens):
        raise MigrationError("Missing DDL target.")
    name = identifier(tokens[position])
    if name.lower().startswith(("pg_", "sql_")) or name.lower() == MANAGEMENT_SCHEMA:
        raise MigrationError("Internal/reserved object names are unsupported.")
    return name, position + 1


def public_target(tokens, position):
    if (position + 2 >= len(tokens) or tokens[position + 1] != "."
            or identifier(tokens[position]) != "public"):
        raise MigrationError("DDL targets must be explicitly qualified in the public schema.")
    name, position = object_name(tokens, position + 2)
    if position < len(tokens) and tokens[position] == ".":
        raise MigrationError("Ambiguous multi-part DDL target.")
    return name, position


def validate_targets(tokens, tables, indexes):
    """Check every relation target in the supported, deliberately narrow grammar."""
    words = [token.upper() if not token.startswith('"') else None for token in tokens]
    forbidden = {"CONCURRENTLY", "INSIGHTSTREAM_MIGRATIONS", "TEMP", "TEMPORARY",
                 "UNLOGGED", "SELECT", "AS", "COMMIT", "ROLLBACK", "BEGIN",
                 "CASCADE", "SCHEMA", "RENAME", "INHERIT", "INHERITS", "PARTITION",
                 "ATTACH", "DETACH", "OF", "LIKE", "OWNER", "TABLESPACE", "SEQUENCE",
                 "CLUSTER", "TRIGGER", "RULE", "POLICY", "EXTENSION"}
    if forbidden.intersection(words) or any(words[i:i + 2] == ["USING", "INDEX"] for i in range(len(words))):
        raise MigrationError("Unsupported migration SQL; indirect/internal DDL targets are forbidden.")

    def optional(position, keywords):
        return position + len(keywords) if words[position:position + len(keywords)] == keywords else position

    prefix = words[:2]
    if prefix == ["CREATE", "TABLE"]:
        name, end = public_target(tokens, optional(2, ["IF", "NOT", "EXISTS"]))
        if tokens[end:end + 1] != ["("] or tokens[-1] != ")":
            raise MigrationError("Only explicit ordinary table definitions are supported.")
        tables.add(name)  # This reviewed declaration approves the new public object.
    elif prefix == ["ALTER", "TABLE"]:
        position = optional(optional(2, ["IF", "EXISTS"]), ["ONLY"])
        name, end = public_target(tokens, position)
        if name not in tables or words[end:end + 1] not in (["ADD"], ["ALTER"], ["DROP"], ["VALIDATE"]):
            raise MigrationError("ALTER TABLE requires an approved application table and supported action.")
    elif prefix == ["CREATE", "INDEX"] or words[:3] == ["CREATE", "UNIQUE", "INDEX"]:
        position = 3 if words[1] == "UNIQUE" else 2
        name, end = object_name(tokens, optional(position, ["IF", "NOT", "EXISTS"]))
        if words[end:end + 1] != ["ON"]:
            raise MigrationError("CREATE INDEX requires an explicit local index name and ON target.")
        table, end = public_target(tokens, optional(end + 1, ["ONLY"]))
        if table not in tables:
            raise MigrationError("Index target is not an approved application table.")
        if words[end:end + 1] == ["USING"]:
            if end + 1 >= len(tokens):
                raise MigrationError("Missing index access method.")
            identifier(tokens[end + 1])
            end += 2
        if tokens[end:end + 1] != ["("]:
            raise MigrationError("Unsupported index definition.")
        indexes.add(name)  # PostgreSQL creates it in the explicitly targeted table's schema.
    elif prefix == ["DROP", "INDEX"]:
        name, end = public_target(tokens, optional(2, ["IF", "EXISTS"]))
        if name not in indexes or words[end:] not in ([], ["RESTRICT"]):
            raise MigrationError("DROP INDEX requires one approved application index; no cascading/multiple targets.")
        indexes.remove(name)
    else:
        raise MigrationError("Unsupported migration SQL; only reviewed transactional table/index DDL is supported.")

    for position, word in enumerate(words):
        if word == "REFERENCES":
            name, _ = public_target(tokens, position + 1)
            if name not in tables:
                raise MigrationError("REFERENCES requires an approved public application table.")


def transactional_statements(source, *, approved_tables=None, approved_indexes=None):
    """Conservative schema-DDL subset, not an attempted general SQL parser.

    Standard quoted literals/identifiers and nested comments are understood.
    Dollar quoting, escaped strings, procedural bodies, transaction/session
    control, data SQL, and nontransactional operations require a separate review.
    Table/reference/drop targets require explicit public qualification. Only
    pinned application objects or objects declared by earlier managed DDL qualify.
    """
    if not source.startswith(HEADER + "\n"):
        raise MigrationError("Migration must declare the transactional header on its first line.")
    pieces, cleaned, start, index = [], [], 0, 0
    while index < len(source):
        char = source[index]
        if source.startswith("--", index):
            end = source.find("\n", index)
            index = len(source) if end < 0 else end
            cleaned.append(" ")
            continue
        if source.startswith("/*", index):
            depth = 1
            index += 2
            while index < len(source) and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise MigrationError("Unterminated SQL comment.")
            cleaned.append(" ")
            continue
        if char in {"'", '"'}:
            quote, value = char, []
            index += 1
            while index < len(source):
                if source[index] == "\\":
                    raise MigrationError("Escaped SQL strings/identifiers are unsupported.")
                if source[index] == quote:
                    if index + 1 < len(source) and source[index + 1] == quote:
                        value.append(quote)
                        index += 2
                        continue
                    break
                value.append(source[index])
                index += 1
            if index >= len(source):
                raise MigrationError("Unterminated SQL quote.")
            cleaned.append(" ? " if quote == "'" else ' "' + "".join(value).replace('"', '""') + '" ')
        elif char in {"$", "\\"}:
            raise MigrationError("Dollar quoting and psql meta-commands are unsupported.")
        elif char == ";":
            if "".join(cleaned).strip():
                pieces.append((source[start:index + 1], "".join(cleaned)))
            cleaned, start = [], index + 1
        else:
            cleaned.append(char)
        index += 1
    if "".join(cleaned).strip():
        raise MigrationError("Each migration statement must end with a semicolon.")
    if not pieces:
        raise MigrationError("Empty migrations are unsupported.")
    baseline_tables, baseline_indexes = application_objects()
    tables = set(baseline_tables if approved_tables is None else approved_tables)
    indexes = set(baseline_indexes if approved_indexes is None else approved_indexes)
    for _, cleaned_sql in pieces:
        tokens = re.findall(r'"(?:[^"]|"")*"|[A-Za-z_][A-Za-z_0-9]*|[^\s]', cleaned_sql)
        validate_targets(tokens, tables, indexes)
    # An invalid file must never expand the next file's allowlist.
    for approved, validated in ((approved_tables, tables), (approved_indexes, indexes)):
        if approved is not None:
            approved.clear()
            approved.update(validated)
    return tuple(statement for statement, _ in pieces)


def repository_state(root=ROOT):
    root = Path(root)
    path = root / "migrations/baseline.json"
    baseline = json.loads(path.read_text())
    if baseline.get("format") != 1:
        raise MigrationError("Unknown baseline manifest format.")
    for filename, expected in baseline["source_checksums"].items():
        if sha256(root / filename) != expected:
            raise MigrationError("Immutable baseline source checksum changed: " + filename)
    historical = {p.name for p in (root / "migrations").glob("*.sql") if p.name != "ledger.sql"}
    if historical != set(baseline["historical_checksums"]):
        raise MigrationError("Unknown/missing historical SQL; new migrations belong in migrations/managed.")
    for filename, expected in baseline["historical_checksums"].items():
        if sha256(root / "migrations" / filename) != expected:
            raise MigrationError("Archived historical migration checksum changed: " + filename)
    found = {}
    for path in sorted((root / "migrations/managed").iterdir()):
        if path.name == "README.md":
            continue
        match = re.fullmatch(r"(\d{3})_([a-z][a-z0-9_]*)\.sql", path.name)
        if not match or not path.is_file() or path.is_symlink():
            raise MigrationError("Unknown managed migration filename.")
        version = int(match[1])
        if version < 16 or version in found:
            raise MigrationError("Duplicate/incompatible managed migration version.")
        found[version] = path
    versions = sorted(found)
    if versions and versions != list(range(16, versions[-1] + 1)):
        raise MigrationError("Missing/out-of-order migration: managed versions must be contiguous from 016.")
    tables, indexes = application_objects(root)
    migrations = []
    for version in versions:
        path = found[version]
        data = path.read_bytes()
        statements = transactional_statements(data.decode("utf-8"), approved_tables=tables, approved_indexes=indexes)
        migrations.append(Migration(version, path.name, hashlib.sha256(data).hexdigest(), statements))
    return baseline, sha256(root / "migrations/baseline.json"), migrations


def inspect(connection, target, root=ROOT):
    verify_target(connection, target)
    baseline, manifest_hash, migrations = repository_state(root)
    if environment_shape(connection) != baseline["environment"]:
        raise MigrationError("Unknown schemas/extensions; baseline validation refused.")
    actual = schema_signature(connection)
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (MANAGEMENT_SCHEMA,))
        registered = cursor.fetchone() is not None
    if not registered:
        profiles = [key for key, value in baseline["profiles"].items() if value["schema_sha256"] == actual]
        if len(profiles) != 1:
            raise MigrationError("Unrecognized application schema; no baseline or migration may be inferred.")
        profile, applied = profiles[0], []
    else:
        if schema_signature(connection, MANAGEMENT_SCHEMA) != baseline["ledger_schema_sha256"]:
            raise MigrationError("Migration ledger structure is unrecognized.")
        with connection.cursor() as cursor:
            cursor.execute("""SELECT version,kind,filename,checksum,baseline_id,provenance,
                schema_sha256 FROM insightstream_migrations.history ORDER BY version""")
            rows = cursor.fetchall()
        if not rows or rows[0][0:2] != (0, "baseline"):
            raise MigrationError("Missing baseline provenance in migration history.")
        first = rows[0]
        profile = first[4]
        if (profile not in baseline["profiles"] or first[2:4] != ("baseline.json", manifest_hash)
                or first[6] != baseline["profiles"][profile]["schema_sha256"]
                or first[5] != {"source_commit": baseline["source_commit"], "historical_execution": "not_asserted"}):
            raise MigrationError("Baseline manifest/provenance checksum mismatch.")
        applied = rows[1:]
        if len(applied) > len(migrations):
            raise MigrationError("Previously applied migration file is missing.")
        for position, (row, migration) in enumerate(zip(applied, migrations), start=1):
            if row[:5] != (migration.version, "migration", migration.filename, migration.checksum, profile):
                raise MigrationError("Migration history/checksum is missing, modified, or out of order.")
            if row[5] != {"previous_schema_sha256": rows[position - 1][6]}:
                raise MigrationError("Migration history schema chain is broken.")
        if actual != rows[-1][6]:
            raise MigrationError("Application schema drifted after the recorded migration/baseline.")
    pending = migrations[len(applied):]
    return {"database": target, "baseline_registered": registered, "baseline_profile": profile,
            "baseline_version": 0, "schema_sha256": actual,
            "applied_versions": [row[0] for row in applied],
            "pending": [{"version": m.version, "filename": m.filename, "checksum": m.checksum,
                         "statement_count": len(m.statements)} for m in pending],
            "historical_execution": "NOT ASSERTED; files 004-015 are never pending",
            "baseline_changes": [] if registered else ["CREATE insightstream_migrations schema/history table", "INSERT one version-0 baseline provenance row"],
            "known_baseline_differences": baseline["differences"]}


def verify_development_backup(path):
    """Require a recent, unchanged, successfully restored private backup."""
    if path is None:
        raise MigrationError("Development writes require --backup-manifest from a recent verified backup.")
    path = Path(path).expanduser().resolve()
    repository = ROOT.parent.resolve()
    if repository == path or repository in path.parents or path.stat().st_mode & 0o077:
        raise MigrationError("Backup manifest must be private and outside the repository.")
    manifest = json.loads(path.read_text())
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(manifest["created_at_utc"])).total_seconds()
    if (not 0 <= age <= 86400 or not manifest.get("verified")
            or not manifest.get("archive_readable") or not all(manifest.get("comparisons", {}).values())):
        raise MigrationError("Backup must be successfully restore-verified within the last 24 hours.")
    if manifest.get("source_database") != "insightstream_db" or sha256(manifest["backup_path"]) != manifest["sha256"]:
        raise MigrationError("Development backup identity/checksum mismatch.")
    verification = json.loads((path.parent / (manifest["verification_database"] + ".json")).read_text())
    if not verification.get("verified") or not all(compare_snapshots(manifest["source_snapshot"], verification["restored_snapshot"]).values()):
        raise MigrationError("Saved restoration verification does not match the backup snapshot.")
    connection = connect(target_url("insightstream_db"))
    try:
        current = snapshot(connection)
    finally:
        connection.rollback()
        connection.close()
    if not all(compare_snapshots(manifest["source_snapshot"], current).values()):
        raise MigrationError("Development changed since the verified backup; take a new backup.")


def execute(connection, target, action, confirmation, profile=None, *,
            approve_development=False, backup_manifest=None, root=ROOT):
    if action not in {"initialize", "baseline", "apply"} or confirmation != target:
        raise MigrationError("An explicit supported action and exact --confirm-target are required.")
    if target == "insightstream_db" and not approve_development:
        raise MigrationError("Development DDL requires separate explicit --approve-development authorization.")
    if action == "initialize" and not target.startswith("insightstream_migrate_"):
        raise MigrationError("Initialization is limited to new disposable migration sandboxes.")
    verify_target(connection, target, write=True)
    connection.rollback()
    if target == "insightstream_db":
        verify_development_backup(backup_manifest)
    baseline, manifest_hash, migrations = repository_state(root)
    connection.set_session(readonly=False, isolation_level="READ COMMITTED", autocommit=False)
    try:
        with connection:
            verify_target(connection, target, write=True)
            with connection.cursor() as cursor:
                for key in ([MIGRATION_LOCK_KEY] if target == "insightstream_db" else [TEST_LOCK_KEY, MIGRATION_LOCK_KEY]):
                    cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", (key,))
                    if not cursor.fetchone()[0]:
                        raise MigrationError("Another migration/test process holds this database's advisory lock.")
                cursor.execute("SET LOCAL lock_timeout='2s'")
                cursor.execute("SET LOCAL statement_timeout='30s'")
                cursor.execute("SET LOCAL search_path=public,pg_catalog")
                if action == "initialize":
                    if environment_shape(connection) != baseline["environment"]:
                        raise MigrationError("Initialization refuses unexpected schemas/extensions.")
                    cursor.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace")
                    if cursor.fetchone()[0]:
                        raise MigrationError("Initialization requires an empty public schema; nothing will be replaced.")
                    cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (MANAGEMENT_SCHEMA,))
                    if cursor.fetchone():
                        raise MigrationError("Initialization refuses an existing management schema.")
                    for name in ("schema.sql", "indexes.sql"):
                        cursor.execute((Path(root) / name).read_text())
                    profile = "declarative"
                state = inspect(connection, target, root)
                if action in {"baseline", "initialize"}:
                    if profile != state["baseline_profile"]:
                        raise MigrationError("Explicit baseline profile does not match the actual schema.")
                    if not state["baseline_registered"]:
                        cursor.execute((Path(root) / "migrations/ledger.sql").read_text())
                        cursor.execute("""INSERT INTO insightstream_migrations.history
                            (version,kind,filename,checksum,baseline_id,provenance,schema_sha256)
                            VALUES(0,'baseline','baseline.json',%s,%s,%s::jsonb,%s)""",
                            (manifest_hash, profile, json.dumps({"source_commit": baseline["source_commit"],
                             "historical_execution": "not_asserted"}), state["schema_sha256"]))
                elif not state["baseline_registered"]:
                    raise MigrationError("Register the verified baseline explicitly before applying migrations.")
                executed = []
                if action in {"apply", "initialize"}:
                    previous = state["schema_sha256"]
                    for migration in migrations[len(state["applied_versions"]):]:
                        for statement in migration.statements:
                            cursor.execute(statement)
                        following = schema_signature(connection)
                        cursor.execute("""INSERT INTO insightstream_migrations.history
                            (version,kind,filename,checksum,baseline_id,provenance,schema_sha256)
                            VALUES(%s,'migration',%s,%s,%s,%s::jsonb,%s)""",
                            (migration.version, migration.filename, migration.checksum,
                             state["baseline_profile"], json.dumps({"previous_schema_sha256": previous}), following))
                        previous = following
                        executed.append(migration.version)
            result = inspect(connection, target, root)
            if action in {"apply", "initialize"} and result["pending"]:
                raise MigrationError("Repository changed during execution; pending batch rolled back.")
        return {**result, "action": action, "executed_now": executed}
    except psycopg2.Error as exc:
        # PostgreSQL DETAIL/CONTEXT can contain SQL literals or row values.
        raise MigrationError("Migration transaction rolled back (SQLSTATE " + (exc.pgcode or "unknown") + ").") from None


def command(args):
    from scripts.migration_database import prepare_checks, verify_url

    if args.migration_action == "prepare-tests":
        return prepare_checks()
    raw = target_url(args.target)
    verify_url(raw, args.target)
    connection = connect(raw)
    try:
        if args.migration_action in {"status", "validate", "preview"}:
            connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout='20s'")
            return inspect(connection, args.target)
        return execute(connection, args.target, args.migration_action, args.confirm_target,
                       args.profile, approve_development=args.approve_development,
                       backup_manifest=args.backup_manifest)
    finally:
        connection.rollback()
        connection.close()
