# Backend Testing Guide

## 1. Purpose

Backend tests verify the current stable read-only API behavior, protect existing endpoints from regressions, and check key seed-data assumptions.

These tests are especially useful now that the backend has a stable API surface, canonical sample data, discovery endpoints, metadata endpoints, and watch-state read endpoints.

## 2. Current Test Scope

The current tests cover read-only endpoints and read-only seed verification only.

Covered areas:

- health endpoint
- content listing
- content type filtering
- recent content
- top-rated content
- genre discovery
- platform discovery
- combined discovery
- homepage sections API
- content details
- content credits endpoint, allowing empty arrays before credits import
- person detail endpoint, conditional on imported people data
- person credits endpoint, conditional on imported people data
- person birthday/place-of-birth response behavior using controlled temporary rows
- person details importer helper behavior for birthday/place-of-birth preview mapping, safe missing-only updates, conflict preservation, and row-level update output
- genre metadata
- platform metadata
- watched read endpoint
- watch later read endpoint
- watch later/watched non-overlap for seeded user
- external IDs seed verification
- TMDb external ID coverage for seeded content
- verified IMDb IDs for all seeded titles
- duplicate external ID checks
- people/cast/crew schema table verification
- person external ID unique constraint verification
- content-person role type constraint verification
- TMDb keyword preview helper behavior
- TMDb keyword retry/merge helper behavior
- TMDb keyword storage schema verification
- TMDb keyword importer dry-run/idempotency helper behavior
- TMDb keyword health-check summary behavior
- keyword-to-signal preview mapping/helper behavior, including v3.2.1 metadata fallback, curated overrides, partial-output protection, semantic QA report fields, generator/QA version fields, product-copy safeguards, v1 reusable mapping rules, v2 config hygiene plus family/emotional, workplace, supernatural, political/crime/survival, historical/war, and mythology/identity cues, and v2.1 period/hotel/caper, social-satire, creature-adventure, superhero-team, mythic, and brisk-investigation cleanup
- source-signal storage schema verification
- source-signal importer dry-run/write/idempotency validation
- source-signal decision-layer display grouping, deduplication, supporting facts, repeated-investigation cleanup, historical/war theme fallbacks, specific caution copy, `best_for` normalization, and public-output sanitization
- decision display quality-audit helper behavior, including issue detection, scoring, grading, CSV formatting, summary aggregation, and fail-threshold logic without live DB/API calls
- source-signal mapping quality-audit helper behavior, including signal richness scoring, missing dimension detection, calibrated caution-proxy diagnostics, backend-display fallback diagnostics, weak/generic labels, stricter subgenre opportunity detection, unmapped keyword opportunities, CSV formatting, summary aggregation, and fail-threshold logic without live DB/API calls
- homepage sections API behavior, including section order, hero quick filters, poster-backed cards, explicit refresh-date handling, bounded deterministic rotation, movie/series freshness ordering, mood-bucket inclusion/exclusion rules, score quality, series-only rails, compact card copy, public-label sanitization, duplicate prevention, and limit clamping
- source-signal ingestion health-check summary behavior

`POST` and `DELETE` mutation tests are intentionally not included yet. Mutation tests should be added later with a safer test-data strategy so local development data is not accidentally changed during read-only test runs.

## 3. Required Database State

Tests assume the local development database has already been prepared using the canonical setup order:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

Expected current seed state:

- 15 total content titles
- 8 movies
- 7 series
- test user: `test@example.com`
- watched: Interstellar, Inception
- watch later: The Mandalorian, Dune: Part Two
- external IDs: 15 `tmdb` rows and 15 verified `imdb` rows
- verified IMDb IDs for all 15 seeded titles
- people/cast/crew schema tables exist with 0 seeded rows until the local people/credits import script is applied
- `people.birthday` and `people.place_of_birth` nullable display-metadata columns are present
- `GET /content/{content_id}/credits` works with either empty credits or imported local credits
- `GET /people/{person_id}` and `GET /people/{person_id}/credits` work when people data has been imported; existing-person tests are skipped when no local people rows exist

If the database is stale, missing seed data, or still has duplicate old seed rows, tests may fail. Reset the local database and rerun the setup SQL files before debugging the tests themselves.

Existing local databases created before person birthday/place-of-birth support
should run `backend/migrations/012_add_person_birthday_birthplace.sql` before
running person endpoint tests.

Some metadata fields are intentionally enriched by later import scripts rather than by
`sample_data.sql` itself. For example, original title/language values can be added by
the TMDb metadata importer after the canonical seed has already created a title. Tests
that validate the canonical seeded catalog should assert only seed-stable fields, while
behavior tests for optional metadata should create controlled temporary rows and clean
them up. This keeps manual metadata imports in a development database from changing
the meaning of a backend test.

## 4. How to Run Tests

From inside the backend folder:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest
```

`pytest` also works if it is available directly:

```bash
pytest
```

Expected current result with local people/credits import applied:

```text
35 passed
```

Without imported people rows, the existing-person endpoint tests are skipped while the 404 tests still run.

## 5. Test File Overview

- `backend/tests/conftest.py` — shared `TestClient` and database fixtures
- `backend/tests/test_health.py` — root health endpoint
- `backend/tests/test_content_read_endpoints.py` — content, discovery, homepage sections, and details read endpoints
- `backend/tests/test_content_credits_endpoints.py` — provider-neutral content credits endpoint
- `backend/tests/test_people_endpoints.py` — provider-neutral person detail and person credits endpoints
- `backend/tests/test_person_metadata_importer.py` — person details preview/import helper behavior
- `backend/tests/test_metadata_endpoints.py` — genre and platform metadata endpoints
- `backend/tests/test_user_content_read_endpoints.py` — watched/watch-later read endpoints for the seeded user
- `backend/tests/test_external_ids_seed.py` — read-only external ID seed verification
- `backend/tests/test_people_schema.py` — read-only people/cast/crew schema verification
- `backend/tests/test_tmdb_keywords_preview.py` — TMDb keyword preview helper tests without live TMDb calls
- `backend/tests/test_tmdb_keywords_retry_merge.py` — TMDb keyword retry/merge helper tests without database writes
- `backend/tests/test_tmdb_keywords_schema.py` — read-only TMDb keyword storage schema verification
- `backend/tests/test_tmdb_keywords_importer.py` — TMDb keyword importer helper tests without database writes
- `backend/tests/test_tmdb_keywords_health_check.py` — TMDb keyword health-check summary tests without database access
- `backend/tests/test_keyword_signal_preview.py` — keyword-to-signal preview mapping, reusable mapping rules, mapping-config hygiene, metadata fallback, curated override, partial-output protection, semantic QA versioning, and product-copy tests without live DB/API calls
- `backend/tests/test_source_signal_schema.py` — source-signal storage schema and index verification
- `backend/tests/test_source_signal_importer.py` — source-signal importer dry-run, write, validation, idempotency, and JSONB helper tests without live DB/API calls
- `backend/tests/test_source_signal_service.py` — source-signal decision-layer sanitization, chip priority, watch profile, compact `decision_layer.display`, supporting facts, global display-quality cleanup, dominant identity selection, overview-assisted theme fallback, repeated-investigation cleanup, historical/war fallback themes, `best_for` normalization, identity/theme/feel dedupe, specific caution wording, and product-friendly decision-copy tests without live DB/API calls
- `backend/tests/test_decision_display_quality_audit.py` — decision display quality-audit helper tests for clean/missing displays, technical leaks, platform-viewer leaks, generic labels, scoring, CSV rows, summary aggregation, and fail flags without DB writes
- `backend/tests/test_source_signal_mapping_quality_audit.py` — source-signal mapping quality-audit helper tests for rich records, missing signals, missing dimensions, calibrated caution-proxy behavior, backend-display fallback diagnostics, common-vs-weak labels, stricter genre/subgenre opportunities, unmapped keyword opportunities, CSV rows, summary aggregation, and fail flags without DB writes

## 6. Important Bug Caught by Tests

The combined discovery endpoint failed for `sort_by=top_rated` when filters were also used.

PostgreSQL raised an error because the query used `SELECT DISTINCT` and ordered by `cs.unified_score`, but that ordered field was not included in the `SELECT` list.

The fix added an internal `sort_unified_score` field for SQL sorting only. `build_content_object()` ignores this internal field, so the API response shape stayed unchanged.

This is a good example of why automated tests are useful: the bug was in SQL behavior, not in the visible response contract, and it was easy to miss during manual endpoint checks.

## 7. Future Testing Work

Future test additions should include:

- mutation tests for `POST /watch-later` and `POST /watched`
- `DELETE` tests for watch later/watched
- invalid input tests
- pagination edge cases
- empty-state tests
- database reset/test isolation later
- recommendation tests when recommendations are added
- richer homepage section tests when personalized recommendation rails are introduced
- frontend/API integration tests later
