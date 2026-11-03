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

The test schema is created from `backend/schema.sql` and `backend/indexes.sql`,
not by replaying the migration directory and not by restoring development.
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
assertion and have the `migration` marker. They require explicit
`--run-migration-tests` permission and are skipped in the ordinary run. Historical
migrations were **not replayed during Milestone 1**, including these tests.
This boundary must remain visible in reported results; the gated tests are not
claimed as executed.

The five November 1 development-data-dependent skips are now covered by fixture
cases: mixed scoring-source tie, missing guidance, missing imported rating,
legacy-only age rating and legacy-only availability. Fixtures also provide
Oppenheimer regional certification, a US-only offer and no-availability records.

Existing pure formatter/mapping/provider helper tests remain database-independent.
Real database tests retain schema, SQL/read API, importer-commit, idempotency,
failure-state and people/search behavior coverage. Database cases are tagged
`database` automatically from their fixture graph.

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
