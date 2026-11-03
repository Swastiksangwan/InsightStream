# Backend Database Setup and Recovery

## Existing development data is not the seed

The preserved local development database is **`insightstream_db`**: PostgreSQL
18.3, 28 public application tables, 200 titles (109 movies / 91 series) at the
November 2, 2026 Milestone 1 baseline. It includes imported ratings, credits,
availability, keywords, source signals and videos.

**Never DROP, reset, truncate or reseed this database to run tests or repair setup.**
The three-file seed reconstructs only 15 titles. Keep development enrichment,
disposable test fixtures and private recovery archives separate.

## Connection precedence

`backend/app/core/config.py` uses exported environment variables first. In normal
`development`/`production` mode it loads the explicit `backend/.env` location with
`override=False`, independent of working directory. It then creates the existing
SQLAlchemy engine through `app.db.session`. Existing application API behavior is
unchanged.

In `test` mode it does not load development dotenv data and requires explicit
`TEST_DATABASE_URL`. Test configuration/actual target is validated before pytest
imports application modules. `unit-test` mode forbids application engine creation.
The test runner loads only the private test configuration, never falls back to
the development URL and never changes the parent shell environment.

Do not print URLs, passwords, provider tokens, `.env` content or database rows.

## Start the existing application on macOS

Use the already configured Python environment and PostgreSQL service:

```bash
cd backend
INSIGHTSTREAM_ENV=development python3 -m uvicorn app.main:app --reload
```

In another terminal, from the repository root:

```bash
cd frontend
npm run dev
```

The default API is `http://127.0.0.1:8000`; frontend is `http://localhost:3000`.
Do not export test settings for an ordinary application server.

## Read-only identity and schema status

From the repository root:

```bash
python3 backend/scripts/local_database.py status
```

This uses only read-only queries and reports database/version, catalog counts,
per-table SHA-256 fingerprints, schema/object counts and source-file hashes.
It explicitly reports migration history as UNTRACKED; presence of a SQL file is
not proof that a migration ran.

## Consistent private backup and verified restore

```bash
python3 backend/scripts/local_database.py backup
```

This command:

1. Requires the explicit local `insightstream_db` target.
2. Opens a repeatable-read, read-only transaction and fingerprints every public
   table, ordered by its primary key, plus schema definitions and sequences.
3. Exports that transaction's PostgreSQL snapshot to `pg_dump --format=custom`.
4. Creates a mode-0600 archive and manifest under a unique mode-0700 directory:
   `~/Library/Application Support/InsightStream/backups/<run>/`.
5. Reads the archive table of contents and calculates SHA-256.
6. Creates a new unique `insightstream_verify_<timestamp>_<suffix>` database.
7. Restores with `--exit-on-error --single-transaction --no-owner --no-privileges`.
8. Requires identical table fingerprints, catalog totals, schema/object counts,
   constraint/index definitions and sequence state before reporting verified.

The tools never pass connection URLs/passwords on command-line arguments. libpq
credentials are scoped to the child environment; errors go to a private log.
The PostgreSQL client must support the server version; a failure stops the
operation. Use a quiet ingestion window: sequence state is not MVCC transactional,
so concurrent writers can cause a conservative verification failure.

The original Milestone 1 backup was restored and verified before test
infrastructure changes. Its private manifest retains the PostgreSQL/client
versions, checksum, complete fingerprints and unique restore target. The dump
contains real development data; do not move it into Git or public artifacts.

To verify that archive again later:

```bash
python3 backend/scripts/local_database.py restore-verify \
  --manifest "$HOME/Library/Application Support/InsightStream/backups/<run>/manifest.json"
```

Replace `<run>` with the recorded directory. This always creates a new database;
there is no replace, clean, drop or arbitrary restore-target option. A checksum
mismatch stops before creating a target. Verification databases are retained;
removing one later requires checking its exact identity and explicit approval.

Compare current development data with a saved baseline without printing rows:

```bash
python3 backend/scripts/local_database.py fingerprint \
  --manifest "$HOME/Library/Application Support/InsightStream/backups/<run>/manifest.json"
```

Every comparison must be true when checking test-induced changes. Intentional
future ingestion changes require a new approved baseline, not editing old hashes.

Schema verification retains raw hashes and narrowly canonicalizes PostgreSQL's
lossless `varchar[] -> text[]` literal-array cast deparser rewrite on restore.
Literal values, constraint names, validation and all other definitions must match.
The November 2 restore had nine such equivalent CHECK representations.

Limitations: `pg_dump` does not include cluster-wide roles/tablespaces. Recovery
verification uses existing local admin credentials and does not reproduce original
ownership/ACLs; it proves application data/schema/sequence restoration, not a
complete server disaster-recovery drill. Private archives require an independent
backup destination/retention policy before treating the laptop as recoverable.

## Disposable test environment

```bash
python3 backend/scripts/local_database.py prepare-test
python3 backend/scripts/local_database.py check-test
python3 backend/scripts/run_tests.py -q -rs
```

Preparation creates only a previously absent `insightstream_test` and dedicated
unprivileged `insightstream_test_runner` role, using the current declarative
schema and indexes. No historical migrations run. Role credentials are generated
locally in private `test.env` (0600), outside Git. The test role can own/modify only
its disposable database; permission checks require no development-table write
or development CREATE privileges. PUBLIC access to the new test database is
revoked. Development privileges/configuration are not modified.

An existing unknown test database/role is inspected and refused, never overwritten.
Do not put development/user data into the marked test target. Test runs reset only
its deterministic 18-title fixture data, including after committed test failures.
See [Backend Testing](backend_testing.md) for isolation, locks, unit-only runs,
explicit test-data reset, and the two gated historical migration tests.

## Declarative baseline and future migration version tracking

The existing baseline is repository commit **`d725576`**, consolidated
`backend/schema.sql` and `backend/indexes.sql`. The live November 2 schema has
28 tables, 271 columns, 239 constraints including PostgreSQL 18 NOT NULL entries,
118 indexes, 170 table/index/sequence objects, and no public routines or triggers.
Fresh test initialization includes the indexes declared in the source files;
four declared indexes are absent in the historical live database. Milestone 1
does not apply them or infer old migration execution.

`backend/migrations/004_...sql` through `015_...sql` are historical SQL files.
There is no reliable migration ledger. **Do not replay the directory** against
existing development data. No new migration framework, ledger or migration apply
command is installed in this milestone.

Proposed small-team approach for the next schema change:

1. Review/approve the live baseline, fingerprint and known index differences.
2. Take and verify a new backup.
3. Review an additive new numbered SQL file, its preconditions and rollback/
   recovery plan on a fresh verification database.
4. Introduce a tiny `schema_migrations` ledger only in that separately reviewed
   change: version, file SHA-256, applied-at and baseline label. Do not fabricate
   historical rows or execute historical files to fill history.
5. Apply each new version exactly once under a transaction and advisory lock;
   reject checksum drift/unknown prerequisites, record success in the same commit.
6. Update the consolidated fresh-database schema/index definitions and relevant
   test fixtures in the same feature branch. Apply schema changes independently
   to each developer's local dev/test targets through that reviewed process.

Until that work is explicitly approved, `status` is diagnostic and there is no
automatic migration application. Fresh database provisioning and versioned
upgrades are different operations.

## Two-developer data workflow

- Each developer has an independently enriched development database and a small
  reproducible test database. Provider tokens remain private.
- Commit schema, fixture and code changes; never commit dumps, private environments
  or generated provider datasets.
- Catalog batches affect development only. Ordinary tests do not synchronize with
  the number of ingested titles or private processed previews.
- Add deterministic fixture records for new behavior and keep genuine independent
  importer/commit coverage. Do not mock database behavior solely to obtain green.
- Back up before approved imports/schema changes; record new baselines afterward.
- Full-catalog restoration is explicit recovery verification, not routine testing.
