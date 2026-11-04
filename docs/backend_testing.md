# Backend Testing Guide

## Safety boundary

Routine tests use **only `insightstream_test`**, with role
`insightstream_test_runner`, on a loopback PostgreSQL server. They never use the
200-title development catalog. Both `INSIGHTSTREAM_ENV=test` and an explicit
`TEST_DATABASE_URL` are required. Missing values do not fall back to `DATABASE_URL`
or `backend/.env`.

Before test modules can import the application's engine, pytest checks the URL,
actual database/user/server, owner, database purpose marker, role privileges,
schema-source hashes and expected tables. The role has no superuser, CREATEDB,
CREATEROLE, replication, bypass-RLS or inherited membership privileges. Permission
inspection must show zero writable development tables and no development CREATE
privilege. No write is attempted against development to test those permissions.

Every SQLAlchemy connection, including independent importer engines, is checked
again. Application configuration rejects a test target outside test mode. Run
pytest in a fresh process: cached application engines imported before the safety
gate are rejected. PostgreSQL URLs are redacted from pytest failure reports.
Managed history and schema signatures are also checked. Pending migrations or
unrecognized drift prevent fixture resets/tests; the runner never auto-migrates
an existing database. Validated managed public tables join fixture resets, while
the separate management history is preserved.

## One-time local preparation

Use the existing macOS PostgreSQL installation and current Python environment.
From the repository root:

```bash
python3 backend/scripts/local_database.py prepare-test
python3 backend/scripts/local_database.py check-test
```

Preparation requires the configured local administrative development connection.
It creates a new role/database only when the names are unused. An existing
unrecognized role/database is a blocker, not permission to overwrite it. An
already prepared environment is inspected without resetting it.

Generated test credentials live in:

```text
~/Library/Application Support/InsightStream/test.env
```

The directory is mode 0700 and the file is 0600. Do not print, commit or send this
file. No real credentials are stored in the repository. The test database owner
is the restricted test role, permitting genuine DDL integration tests in this
disposable database without granting privileges over development.

## Run tests

From the repository root:

```bash
# Full ordinary suite; private test settings are loaded explicitly by this runner.
python3 backend/scripts/run_tests.py -q -rs

# Pure tests without a running PostgreSQL server or any database URL.
python3 backend/scripts/run_tests.py --unit-only -q

# Narrow a run normally.
python3 backend/scripts/run_tests.py backend/tests/test_search_endpoints.py -q
```

The runner removes inherited development/provider credentials from the child
process. Explicit exported test settings override the private file, and unsafe
settings still fail the guard. A bare `python3 -m pytest` without explicit test
configuration intentionally fails before collection. `--unit-only` deselects
cases whose fixture graph requires the database/client and refuses application
engine initialization.

Both repository-root and `cd backend` invocations work. From backend, use
`python3 scripts/run_tests.py -q`.

## Deterministic fixtures and genuine commits

The test schema starts from the pinned `backend/schema.sql` and
`backend/indexes.sql`, with managed versions included when preparing a new test
database. Historical files are not replayed and development is not restored.
The fixture is the canonical 15-title `backend/sample_data.sql` plus
`backend/tests/fixtures/catalog.sql`: 18 titles, synthetic source ratings,
selected people/credits, lifecycle, source signals, regional offers and deliberate
missing-data cases. Registry definitions are explicitly reseeded after data reset.
All fixture timestamps are fixed. Provider-derived seed images are not fetched.
Synthetic ratings are test inputs, never catalog ingestion.

For each database test, the guarded fixture resets only the known test tables
using TRUNCATE/RESTART IDENTITY, then reloads these small deterministic records.
It resets again in `finally`, after sessions/clients close. This is deliberate:
existing integration tests exercise independent connections and real commits, so
an outer rollback cannot isolate all writes. Assertions and importer behavior
are retained; everything is confined to the disposable test database.

A session advisory lock prevents concurrent suites/resets on one local database.
Parallel pytest workers are not supported. A killed process may leave test data;
inspect identity and use the explicit reset below. Unexpected tables/schema-source
drift cause refusal rather than an automatic schema rebuild.

```bash
python3 backend/scripts/local_database.py check-test
python3 backend/scripts/local_database.py reset-test --confirm-reset insightstream_test
```

Reset operates only on marked `insightstream_test`, checks development write
permissions, takes the same lock, and requires the exact target name as explicit
operator confirmation. There is no development-reset command. A regular test run
also resets disposable fixture data; never put personal/development data there.

## Historical migrations and skips

The two existing video migration idempotency/preservation tests retain every
assertion and the `migration` marker. Their original shared-database cases remain
skipped. Historical migrations were **not replayed during Milestone 1**.

Milestone 2A executes both original functions, with their original assertions,
through `test_original_historical_assertions_execute_only_on_new_disposable_database`
on a newly initialized sandbox. This reveals that 015 adds a second equivalent
retry-count CHECK to the consolidated fresh schema. The migration ledger correctly
reports that replay as drift rather than marking it as managed execution. Routine
test/development schemas are not changed. The old `--run-migration-tests` flag now
fails before database access; use the controlled lifecycle checks below.

The five November 1 development-data-dependent skips are now covered by fixture
cases: mixed scoring-source tie, missing guidance, missing imported rating,
legacy-only age rating and legacy-only availability. Fixtures also provide
Oppenheimer regional certification, a US-only offer and no-availability records.

Existing pure formatter/mapping/provider helper tests remain database-independent.
Real database tests retain schema, SQL/read API, importer-commit, idempotency,
failure-state and people/search behavior coverage. Database cases are tagged
`database` automatically from their fixture graph.

## Migration management checks

Create fresh targets, then use the exact private JSON path printed by preparation:

```bash
python3 backend/scripts/local_database.py migrations prepare-tests
MIGRATION_CHECKS="$HOME/Library/Application Support/InsightStream/migration-checks/<run>.json"

# Full backend suite, including the three disposable lifecycle checks:
python3 backend/scripts/run_tests.py --migration-env "$MIGRATION_CHECKS" -q -rs
```

For a migration-only run, prepare a **new** configuration and add
`backend/tests/test_migration_management.py` to the runner arguments. Reading a
configuration revalidates identity but does not consume it or prevent rereading.
Fresh targets are required for each lifecycle run because initialization refuses
nonempty schema state. No migration database is reset or deleted automatically.
Without `--migration-env`, the three lifecycle cases explicitly skip. Pure
migration safety tests and the shared-test-lock check still run normally.
`--unit-only` deselects every database case, including migration sandboxes.

The fresh lifecycle covers initialization/baseline provenance, successful schema
changes, idempotency, modified/missing files, whole-batch rollback, advisory-lock
contention, data preservation, corrupt history and unrecorded schema drift. The
existing-schema case uses a schema-only clone with the exact live profile and
proves no automatic index repair. Historical checks call the original test
functions on a third new database. Pure cases cover unsupported/nontransactional
SQL, explicit public-schema object allowlists (including quoted identifiers),
configuration rereading, duplicate/gapped versions, immutable source checksums, unknown/forged targets,
backup evidence and protection from development credentials. The shared fixture
check proves the suite lock blocks test-schema migrations before DDL.

See [Database Setup and Recovery](backend_database_setup.md#migration-management-baseline-and-history)
for the canonical migration commands, SQL subset, two baseline profiles and later
approval procedure. Sandbox credentials/archives stay outside Git; created
databases are retained pending separately approved cleanup.

## Existing regression history and references

An early combined-discovery regression used `SELECT DISTINCT` with
`ORDER BY cs.unified_score` without selecting that sort expression. PostgreSQL
rejected filtered `sort_by=top_rated` queries. The existing fix selects an internal
`sort_unified_score` value while `build_content_object()` preserves the public
response shape. This history remains a reason to retain genuine PostgreSQL
endpoint coverage alongside pure tests.

Formatter test ownership, public-field consistency rules, and diagnostic commands
remain documented in [Decision Insight Formatter v2](decision_insight_formatter_v2.md).
The read-only catalog expansion audit is documented in
[Catalog Expansion Readiness](catalog_expansion_readiness.md); generated audit
reports are evidence, not ordinary test fixtures.

## Validation and two-developer workflow

Before changing fixtures or schema, run the safety unit tests and `check-test`.
Developers each prepare their own local test database once; no manual
synchronization with development ingestion is needed. Catalog expansion must not
change ordinary test counts or expectations. Add a small explicit fixture for a
new behavior, not a production dump.

Full-catalog recovery is a separate `backup`/`restore-verify` workflow in
[Backend Database Setup](backend_database_setup.md); it is never an implicit
pytest fixture. Future snapshot-based integration tests must have their own
explicit isolated targets and authorization.

November 2, 2026 validation: **876 passed, two skipped** (the explicitly gated
migration cases), versus the original 829 passed / five skipped baseline.
The unit-only run passed **747 tests**, deselecting 131 database cases, without
PostgreSQL access. Forty-four safety/isolation cases were added; all five former
fixture-dependent skips now execute. An intentional committed-test failure also
verified cleanup. Development counts, row fingerprints, schema and sequences
matched the pre-change snapshot. The two gated migration cases were not executed.

November 4, 2026 Milestone 2A validation: **928 passed / two intentionally skipped**
with a fresh migration configuration, including **52 migration-management cases**.
The original historical assertions passed inside the sandbox lifecycle; their
two shared-schema entries remain skipped. Unit-only validation passed **795 tests**
with 135 database cases deselected. The frontend production build passed. The
existing urllib3/LibreSSL warning remains; no dependencies were installed/changed.
