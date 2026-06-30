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
- content details
- content credits endpoint, allowing empty arrays before credits import
- person detail endpoint, conditional on imported people data
- person credits endpoint, conditional on imported people data
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
- `GET /content/{content_id}/credits` works with either empty credits or imported local credits
- `GET /people/{person_id}` and `GET /people/{person_id}/credits` work when people data has been imported; existing-person tests are skipped when no local people rows exist

If the database is stale, missing seed data, or still has duplicate old seed rows, tests may fail. Reset the local database and rerun the setup SQL files before debugging the tests themselves.

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
- `backend/tests/test_content_read_endpoints.py` — content, discovery, and details read endpoints
- `backend/tests/test_content_credits_endpoints.py` — provider-neutral content credits endpoint
- `backend/tests/test_people_endpoints.py` — provider-neutral person detail and person credits endpoints
- `backend/tests/test_metadata_endpoints.py` — genre and platform metadata endpoints
- `backend/tests/test_user_content_read_endpoints.py` — watched/watch-later read endpoints for the seeded user
- `backend/tests/test_external_ids_seed.py` — read-only external ID seed verification
- `backend/tests/test_people_schema.py` — read-only people/cast/crew schema verification
- `backend/tests/test_tmdb_keywords_preview.py` — TMDb keyword preview helper tests without live TMDb calls
- `backend/tests/test_tmdb_keywords_retry_merge.py` — TMDb keyword retry/merge helper tests without database writes

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
- frontend/API integration tests later
