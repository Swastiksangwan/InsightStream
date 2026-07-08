# InsightStream

## 1. Project Overview

InsightStream / CineLens is an information-first entertainment decision-support platform for movies and series.

The current MVP focuses on structured metadata, discovery, availability, personal watch state, cast and crew, and person pages. The product is designed to help users decide what to watch by making content data easier to inspect and compare.

Ratings and review intelligence are planned later. Public reviews, comments, posts, communities, followers, and social feeds are not part of the current MVP.

## 2. Current Phase

Current phase: **Metadata Foundation**

Completed:

- 15-title movie/series seed catalog.
- Content listing, details, discovery, genres, platforms, and personal watch-state APIs.
- Local catalog search for ingested content and imported people.
- Real poster/backdrop URLs persisted in `backend/sample_data.sql`.
- Provider-neutral `external_ids` table with TMDb and IMDb IDs.
- Metadata normalization and reconciliation docs.
- Safe normalized metadata updates for genre additions and series status values.
- People/cast/crew schema: `people`, `person_external_ids`, and `content_people`.
- Structured credits preview and safe people/credits import.
- TV aggregate credits support for series cast, with regular TV credits as fallback.
- Person detail/biography preview and safe biography import.
- Backend APIs for content credits, person detail, and person credits.
- Redesigned content detail page with metadata, availability, ratings, cast/crew, and watch actions.
- Clickable genre chips to filtered discovery.
- Clickable person cards and person detail pages with biography and filmography.
- Small TMDb attribution footer in the frontend.
- TMDb keyword preview pipeline with retry/merge workflow for future source signals.
- Source-signal decision layer in the content detail API, including compact, rule-cleaned `decision_layer.display` output while keeping raw keywords internal.
- Decision display quality audit script for catalog-wide QA of `decision_layer.display` scores, issues, and review candidates.
- Source signal mapping quality audit script for stored signal richness, genre/subgenre gaps, calibrated fallback/caution diagnostics, and unmapped keyword opportunities.

Next planned:

- `latest_activity_date` for better Recent sorting, especially for active series.
- Scalable metadata ingestion plan before expanding to 100+ titles.
- Ratings source architecture.
- Rating normalization and unified score strategy.
- Further frontend polish around compact `decision_layer.display`.
- Review intelligence, pros/cons, and verdict pipeline.

## 3. Tech Stack

Backend:

- FastAPI
- PostgreSQL
- SQLAlchemy sessions with raw SQL via `text()`
- Pydantic response schemas
- pytest

Frontend:

- Next.js
- React
- TypeScript
- CSS-based dark cinematic UI

Analytics and ingestion:

- TMDb as the current prototype/non-commercial metadata provider
- Processed preview files under `analytics/processed/tmdb/`
- Local raw provider files under `analytics/raw/tmdb/` ignored by git
- Dry-run/apply scripts for controlled local imports
- Provider-neutral database model so TMDb can be replaced later
- TMDb keyword preview/retry/merge workflow documented in `docs/data_ingestion_pipeline.md`

## 4. Core Features Implemented

Content:

- Content listing
- Local search across ingested content titles, overviews, content types, and genres
- Content detail responses
- Discovery filtering by type, genre, platform, availability, and sort mode
- Genre and platform metadata
- Recent and top-rated feeds
- Watch Later and Watched actions

Metadata:

- Real posters and backdrops for seeded titles
- TMDb and IMDb external IDs
- Normalized genre additions
- Improved series status values
- Content credits: cast, directors, creators, and crew
- Person records with provider-neutral external IDs
- Person biographies from processed provider preview
- Person filmography from imported content-person relationships

Frontend:

- Homepage
- Local search page
- Discovery page
- Content detail page
- Watch Later page
- Watched page
- Person detail page
- Clickable genre chips to `/discover?genre=<GenreName>`
- Clickable person cards to `/people/[id]`
- Fallback poster, backdrop, and avatar states

## 5. Backend API Summary

Content:

- `GET /search`
- `GET /content`
- `GET /content/{content_id}`
- `GET /content/{content_id}/details`
- `GET /content/recent`
- `GET /content/top-rated`
- `GET /content/discover`
- `GET /content/by-genre/{genre_name}`
- `GET /content/by-platform/{platform_name}`

`GET /content/{content_id}/details` includes ratings, availability, Insight Summary, and a nullable source-signal `decision_layer` when stored watch guidance exists. `decision_layer.display` is the preferred compact frontend contract; older `watch_profile` and `decision_support` fields remain for compatibility. The backend ranks, dedupes, sanitizes, and applies deterministic dominant-identity rules before returning display labels, so raw TMDb keywords, weak platform/viewer labels, repeated investigation phrasing, and source-signal debug metadata are not exposed by default. New frontend work should prefer `ratings`, `insight_summary`, `availability`, and `decision_layer.display`; the legacy `summary` object remains for backward compatibility.

Metadata:

- `GET /genres`
- `GET /platforms`

Watch state:

- `POST /watch-later`
- `DELETE /watch-later`
- `GET /watch-later/{user_id}`
- `POST /watched`
- `DELETE /watched`
- `GET /watched/{user_id}`

Credits:

- `GET /content/{content_id}/credits`

People:

- `GET /people/{person_id}`
- `GET /people/{person_id}/credits`

Backend API docs are available at:

```text
http://127.0.0.1:8000/docs
```

Search uses the local PostgreSQL catalog only. It covers ingested content,
imported people, and content connected to people through cast, crew, director,
and creator credits. It does not call TMDb or any other live provider. Missing
titles or people must first be added through the ingestion pipeline.

## 6. Database Setup

The local database is built from SQL files in this order:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

What each file does:

- `schema.sql` creates tables, constraints, and relationships.
- `sample_data.sql` creates the canonical 15-title seed data.
- `indexes.sql` adds performance indexes.

The base seed restores content, genres, platforms, ratings, summaries, external IDs, watch-state examples, and real poster/backdrop URLs for the current seeded titles.

People, credits, and person biographies are imported after the base seed using analytics scripts. They are not inserted directly by `sample_data.sql`.

For the current ingestion layer map, full metadata rebuild flow, series refresh workflow, ratings imports, and TMDb keyword preview/retry/merge workflow, use `docs/data_ingestion_pipeline.md`.

## 7. Environment Variables

Required depending on task:

```env
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db_name>
TMDB_READ_ACCESS_TOKEN=<tmdb_read_access_token>
```

Notes:

- `DATABASE_URL` is required by the backend and database import scripts.
- `TMDB_READ_ACCESS_TOKEN` is required only when fetching provider data from TMDb.
- Do not commit API keys, tokens, or local `.env` files.
- The frontend can optionally use `NEXT_PUBLIC_API_BASE_URL`; otherwise it defaults to `http://127.0.0.1:8000`.

## 8. Ingestion / Metadata Scripts

Run scripts from the repository root.

`analytics/scripts/fetch_tmdb_sample.py`

- Fetches TMDb metadata for the 15 seeded titles.
- Writes raw ignored JSON under `analytics/raw/tmdb/`.
- Writes processed preview data to `analytics/processed/tmdb/sample_mapping_preview.json`.
- Fetches TV aggregate credits for series where available.
- Makes no database writes.

`analytics/scripts/update_posters_from_tmdb_preview.py`

- Reads the processed TMDb title preview.
- Updates only `poster_url` and `backdrop_url`.
- Dry-run by default; requires `--apply` for database writes.
- Mostly useful now for refresh, repair, or new titles because current seed data already has verified poster/backdrop URLs.

`analytics/scripts/build_tmdb_credits_preview.py`

- Builds a provider-neutral credits preview at `analytics/processed/tmdb/credits_preview.json`.
- Reads existing raw TMDb files.
- Uses TV aggregate credits for series cast when available.
- Keeps regular TV credits as fallback.
- Makes no database writes.

`analytics/scripts/import_people_credits_from_preview.py`

- Imports `people`, `person_external_ids`, and `content_people`.
- Reads `analytics/processed/tmdb/credits_preview.json`.
- Dry-run by default; requires `--apply` for database writes.
- Reuses existing people by provider external ID and avoids duplicate relationships.

`analytics/scripts/fetch_tmdb_person_details.py`

- Reads local `person_external_ids` where `source_name = 'tmdb'`.
- Fetches TMDb person details and biographies.
- Writes `analytics/processed/tmdb/person_details_preview.json`.
- Makes no database writes.

`analytics/scripts/import_person_details_from_preview.py`

- Imports only missing safe person fields: `biography`, `profile_url`, and `known_for_department`.
- Never overwrites non-empty existing values.
- Dry-run by default; requires `--apply` for database writes.

Analysis/reporting scripts:

- `analytics/scripts/analyze_tmdb_metadata_gap.py`
- `analytics/scripts/reconcile_basic_metadata.py`

These compare seed data with processed provider previews and generate reports. They do not update PostgreSQL.

## 9. Full Database Reset / Restore Flow

For the current metadata catalog rebuild and ingestion flow, follow `docs/data_ingestion_pipeline.md`.

For a clean local reset in pgAdmin or `psql`:

```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

Then run:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

Set environment variables before import scripts:

```bash
export DATABASE_URL="postgresql://<user>:<password>@localhost:5432/<db_name>"
export TMDB_READ_ACCESS_TOKEN="..."
```

If processed files already exist:

```bash
python3 analytics/scripts/import_people_credits_from_preview.py --apply
python3 analytics/scripts/import_person_details_from_preview.py --apply
```

If regenerating provider data:

```bash
python3 analytics/scripts/fetch_tmdb_sample.py
python3 analytics/scripts/build_tmdb_credits_preview.py
python3 analytics/scripts/import_people_credits_from_preview.py --apply
python3 analytics/scripts/fetch_tmdb_person_details.py
python3 analytics/scripts/import_person_details_from_preview.py --apply
```

Poster/backdrop URLs are already restored by `backend/sample_data.sql` for the current 15 titles. Use `update_posters_from_tmdb_preview.py` only for refresh, repair, or new title work.

## 10. Running Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Windows, activate the virtual environment with the equivalent script for your shell.

## 11. Running Frontend

```bash
cd frontend
npm install
npm run dev
```

Build check:

```bash
npm run build
```

Frontend app:

```text
http://localhost:3000
```

## 12. Testing

Backend:

```bash
cd backend
python3 -m pytest
```

Frontend:

```bash
cd frontend
npm run build
```

All tests and builds should pass with the local database prepared from `schema.sql`, `sample_data.sql`, and `indexes.sql`. People/person endpoint tests are designed to handle a database before or after the people/credits import.

## 13. Current Limitations / Not Yet Implemented

- Scalable ingestion for 100+ titles is not finalized yet.
- `latest_activity_date` recency sorting is planned but not implemented.
- Ratings source architecture is not finalized.
- Review intelligence is not implemented.
- Current ratings, summaries, pros, cons, verdicts, and unified scores are development seed data.
- No public social/community layer exists in the MVP.
- No episode-level credits model exists yet.
- No frontend code calls TMDb directly.
- No broad season/episode schema exists yet.

## 14. Roadmap

1. Implement `latest_activity_date` for Recent sorting.
2. Create a scalable metadata ingestion plan.
3. Expand the catalog safely beyond 15 titles.
4. Plan ratings source architecture.
5. Implement rating normalization and unified score calculation.
6. Add review intelligence, pros/cons, and verdict pipeline.
7. Improve discovery and ranking.

## Documentation

Useful current docs:

- `docs/product_direction.md`
- `docs/README.md`
- `docs/backend_database_setup.md`
- `docs/backend_testing.md`
- `docs/data_ingestion_pipeline.md`
- `docs/metadata_provider_strategy.md`
- `docs/metadata_normalization_plan.md`
- `docs/content_recency_sorting_plan.md`
- `docs/person_cast_crew_schema_plan.md`
- `docs/metadata_navigation_plan.md`
- `docs/ratings_foundation_plan.md`
- `docs/insight_summary_foundation_plan.md`
- `docs/source_signal_research_findings.md`

## MVP Boundary

InsightStream / CineLens is not a public social or community platform in the current MVP. User interaction is personal and utility-focused through Watch Later and Watched. Public reviews, posts, comments, followers, communities, likes, and feeds are intentionally excluded while the project focuses on structured entertainment metadata, discovery, analytics, and decision support.
