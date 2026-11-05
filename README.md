# InsightStream

## 1. Project Overview

InsightStream is an information-first entertainment decision-support platform for movies and series.

The working local MVP combines structured metadata, discovery, regional availability, aggregate audience ratings, deterministic decision insights, personal watch state, and cast/crew/person pages. The product is designed to help users decide what to watch by making content data easier to inspect and compare.

Aggregate ratings are implemented. Individual review ingestion and review-derived intelligence are not implemented; current decision insights come from metadata, ratings, and mapped source signals. Public reviews, comments, posts, communities, followers, and social feeds are outside the current MVP.

## 2. Current Phase

Current phase: **Working local MVP — recovery and data/pipeline stabilization**

The November 1, 2026 read-only recovery audit at `d725576` verified a 200-title
development catalog, not just the original seed. These are dated audit measurements,
not guarantees of provider freshness or production readiness:

| Area | Verified November 1 state |
| --- | --- |
| Catalog | 200 titles: 109 movies / 91 series, across 28 application tables |
| Aggregate ratings | TMDb: 200 titles; IMDb: 150; Letterboxd: 79 of 109 movies |
| External identifiers | TMDb and IMDb IDs on all 200 titles; an ID does not imply a stored rating |
| Credits and guidance | Cast and stored watch guidance on all 200 titles; creators on 80 of 91 series |
| Availability and videos | Regional availability on 198 titles; a selected primary video on 199 |

Milestone 1 established verified private backups and an isolated, deterministic
PostgreSQL test environment. Its full backend validation passed **876 tests with
two intentional historical-migration skips**, versus the November 1 baseline of
829 passed / five skipped. The frontend production build and application smoke
checks passed. Development data remained at 200 titles with matching integrity
fingerprints. See [database recovery](docs/backend_database_setup.md) and
[testing evidence and skip reasons](docs/backend_testing.md).

Milestone 2A adds explicit baseline validation and transactional migration tracking.
Development was unregistered during implementation; the November 5 inspection
verified subsequent version-0 registration of the accepted `live` profile, with
no managed migrations applied. Historical SQL is archived, not inferred as run.
November 4 validation, including the DDL-target review correction, passed
**988 tests / two intentional skips**, **855 pure
tests**, and the frontend production build. The two archived cases' original
assertions also passed through a dedicated disposable sandbox lifecycle.

Milestone 2B corrects catalog refresh diagnostics and separates stored data,
historical collection, freshness and retry eligibility. The November 5 read-only
observation found 36 series targets and 200 video targets due under existing
rules; it performed no refresh or import. See the
[catalog diagnostics and refresh lifecycle audit](docs/catalog_diagnostics_refresh_audit_2026_11_05.md)
for current coverage, source limitations, verification and the recovery sequence.

Completed:

- 200-title imported local catalog, alongside the original canonical 15-title seed used for fresh setup and deterministic tests.
- Content listing, details, discovery, genres, platforms, and personal watch-state APIs.
- Local catalog search for ingested title/original-title matches and imported people names.
- Real poster/backdrop URLs persisted in `backend/sample_data.sql`.
- Provider-neutral `external_ids` table with TMDb and IMDb IDs.
- Metadata normalization and reconciliation docs.
- Safe normalized metadata updates for genre additions and series status values.
- `latest_activity_date` Recent sorting and series lifecycle/season/episode counters.
- Provider-neutral aggregate rating sources, TMDb/IMDb/Letterboxd importers, normalized scores, and calculated unified scores.
- Deterministic Insight Summary from ratings and metadata; this is separate from review analysis.
- People/cast/crew schema: `people`, `person_external_ids`, and `content_people`.
- Structured credits preview and safe people/credits import.
- TV aggregate credits support for series cast, with regular TV credits as fallback.
- Person detail/biography preview and safe biography import.
- Backend APIs for content credits, person detail, and person credits.
- Redesigned content detail page with metadata, availability, ratings, cast/crew, and watch actions.
- Clickable genre chips to filtered discovery.
- Clickable person cards and person detail pages with biography and filmography.
- Small TMDb attribution footer in the frontend.
- Stored video metadata, deterministic primary-video selection, and trailer/teaser UI with failure/empty states.
- Shared manual series/video refresh planning and execution with per-domain outcomes.
- TMDb keyword preview pipeline with retry/merge workflow for future source signals.
- Source-signal decision layer in the content detail API, including compact, rule-cleaned `decision_layer.display` output while keeping raw keywords internal.
- Backend-powered homepage sections API with deterministic weekly/daily rotation and a frontend homepage that consumes it directly.
- Decision display quality audit script for catalog-wide QA of `decision_layer.display` scores, issues, and review candidates.
- Source signal mapping quality audit script for stored signal richness, genre/subgenre gaps, calibrated fallback/caution diagnostics, and unmapped keyword opportunities.
- Read-only catalog expansion-readiness audit for composition, metadata, keyword/signal quality, refresh health, recommendation candidate density, discovery coverage, expansion gaps, and optional query-plan baselines.
- Source signal mapping improvements v1 for reusable pacing, mood, survival, war, space-sci-fi, post-apocalyptic, kitchen-workplace, investigation, AI, and mythic/future-society signal quality.
- Source signal mapping improvements v2 for config hygiene plus family/emotional, workplace, supernatural, political/crime/survival, historical/war, nature-documentary, and mythology/identity signal coverage.
- Source signal mapping improvements v2.1 for targeted remaining-candidate cleanup and stricter subgenre false-positive protection.
- Runtime Decision Insight Formatter v2.0.2 with evidence-based compact copy and regression coverage.
- Dedicated test database/role, early connection guards, deterministic commit-safe fixtures, and private backup/restore verification tools.
- Versioned migration tooling with two verified baseline profiles, checksummed history, preview, confirmation/backup gates, transactional batches and advisory locks.

Next planned:

- Complete and validate existing rating matches before adding more catalog titles.
- Reconcile stale availability and stabilize repeatable ingestion/refresh workflows.
- Review source-signal quality and remaining schema/index differences using audit evidence.
- Establish prerequisites for controlled catalog expansion; batches 8–10 remain un-ingested in the audited snapshot.

Review intelligence remains optional future work requiring a supported data source
and verified provider access/licensing. It is not a dependency of the working MVP.

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
- Local search across ingested content titles, original titles, and imported people names
- Content detail responses
- Discovery filtering by type, genre, platform, availability, and sort mode
- Genre and platform metadata
- Recent and top-rated feeds
- Six deterministic backend homepage rails, consumed by the frontend with a five-minute homepage cache
- Watch Later and Watched actions

Metadata:

- Persisted posters and backdrops for the imported catalog
- TMDb and IMDb external IDs
- Original title/language and series freshness/lifecycle metadata
- Normalized genre additions
- Improved series status values
- Regional streaming/rent/buy/free/ad-supported offers and certifications
- TMDb/IMDb/Letterboxd aggregate ratings and a normalized unified score
- Mapped keyword signals and deterministic compact watch-fit insights
- Stored trailers/teasers and a selected primary video
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

The unified score uses active, positive-weight sources with at least 50 votes.
At the audited baseline TMDb and IMDb have equal weight; Letterboxd ratings are
displayed separately with zero unified-score weight. Ratings are aggregate audience
scores, not individual reviews. Watch actions currently use a demo user; there is
no authentication or personalized recommendation system.

## 5. Backend API Summary

Content:

- `GET /search`
- `GET /content`
- `GET /content/{content_id}`
- `GET /content/{content_id}/details`
- `GET /content/recent`
- `GET /content/top-rated`
- `GET /content/home`
- `GET /content/discover`
- `GET /content/by-genre/{genre_name}`
- `GET /content/by-platform/{platform_name}`

`GET /content/{content_id}/details` includes ratings, availability, Insight Summary, and a nullable source-signal `decision_layer` when stored watch guidance exists. `decision_layer.display` is the authoritative compact frontend contract; older `watch_profile` and `decision_support` fields remain for compatibility but reuse the same runtime Formatter v2 sentence. The backend builds "Why this stands out" copy at read time through a deterministic evidence plan: specific identities, governed concept families, safe copy roles, controlled overview rules, and non-random sentence templates. A formatter code change therefore requires no guidance-table sentence rewrite. Raw TMDb keywords, unsupported fallback labels, weak platform/viewer labels, repeated concepts, and source-signal debug metadata are not exposed by default. New frontend work should prefer `ratings`, `insight_summary`, `availability`, and `decision_layer.display`; the legacy `summary` object remains for backward compatibility.

The complete generation, safety, debugging, readiness, and version contract is in
[`docs/decision_insight_formatter_v2.md`](docs/decision_insight_formatter_v2.md).

`GET /content/home` returns a backend-assembled homepage contract consumed by the frontend homepage. It includes hero quick filters and, in order, `weekly_picks`, `top_rated`, `recent_releases`, `mood_pace`, `platform_picks`, and `binge_worthy_series`. The public recent rail is titled `New & Recently Active` because it uses movie release dates plus series freshness metadata. Homepage cards are poster-led, so section candidate queries require poster-backed content. Weekly picks rotate by ISO week; top-rated, mood/pace, platform, and series rails rotate deterministically by the Asia/Kolkata calendar date. Mood/pace buckets use source-signal inclusion and exclusion rules so darker titles do not leak into light-watch rails. Platform buckets are curated to recognizable labels such as Netflix, Prime Video, JioHotstar, Apple TV+, and YouTube when those platforms exist locally. Existing `/content/top-rated`, `/content/recent`, and discovery endpoints remain available. The endpoint is recommendation-ready but not personalized yet.

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

Search uses the local PostgreSQL catalog only. Ordinary search is intentionally
strict and predictable: title results match `content.title` or
`content.original_title`, and people results match `people.name`. It does not
match overview text, genres, biographies, departments, credits, platforms, or
source-signal metadata for normal results. Results are ranked deterministically
by exact match, starts-with match, word-start match, then contains match, with
stable title/name ordering as a tie-breaker. It does not call TMDb or any other
live provider. Richer description, genre, credit, or semantic search can be
added later as an explicit advanced-search mode.

## 6. Database Setup

The preserved local development catalog has 200 titles. The canonical seed below
contains only 15 and must never be used to reset the enriched development database.
Use [the safe database workflow](docs/backend_database_setup.md) for private verified
backups and [isolated testing](docs/backend_testing.md).

For a new empty database only, the declarative seed setup order is:

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
TMDB_LANGUAGE=en-US
TMDB_VIDEO_LANGUAGES=en,null
```

Notes:

- `DATABASE_URL` is required by the backend and database import scripts.
- Normal backend startup uses `INSIGHTSTREAM_ENV=development` (the default), exported variables first, then `backend/.env` with `override=False`.
- Tests require `INSIGHTSTREAM_ENV=test` and `TEST_DATABASE_URL`. The safe runner loads these from a private file outside Git; do not export them for the development server or add them to its `.env`.
- `TMDB_READ_ACCESS_TOKEN` is required only when fetching provider data from TMDb.
- `TMDB_LANGUAGE` controls localized TMDb detail/video metadata and defaults to `en-US`.
- `TMDB_VIDEO_LANGUAGES` controls appended video-language fallbacks. It accepts a
  bounded, comma-separated list of ISO 639-1 codes plus TMDb's `null` token. The
  configured detail-language base code remains the primary-video ranking preference;
  a known title original language expands the request but does not replace it.
- Do not commit API keys, tokens, or local `.env` files.
- The frontend can optionally use `NEXT_PUBLIC_API_BASE_URL`; otherwise it defaults to `http://127.0.0.1:8000`.

## 8. Ingestion / Metadata Scripts

Run scripts from the repository root.

`analytics/scripts/ingestion/fetch_tmdb_sample.py`

- Fetches TMDb metadata and appended video records for configured titles.
- Writes raw ignored JSON under `analytics/raw/tmdb/`.
- Writes processed preview data to `analytics/processed/tmdb/sample_mapping_preview.json`.
- Writes transient video failures to a bounded retry artifact and permanent
  source/normalization issues to a separate manual-review artifact under the ignored
  TMDb run-report directory.
- Uses one movie/TV detail request with `append_to_response=videos`; it does not make a separate videos request.
- Sends `include_video_language` from `TMDB_VIDEO_LANGUAGES` and fingerprints
  response-affecting request parameters before reusing a raw cache entry.
- Uses bounded batches/concurrency and bounded retries for transient failures.
- Fetches TV aggregate credits for series where available.
- Makes no database writes.

`analytics/scripts/refresh/build_content_refresh_plan.py`

- Builds the ignored, PostgreSQL-backed refresh plan for `series_metadata`, `videos`,
  or both scopes without provider requests or database writes.
- Reuses the existing series planner decision function and existing video fetch state.

`analytics/scripts/refresh/run_content_refresh.py`

- Supports mutually exclusive `--plan-only`, `--dry-run`, and `--apply` modes.
- Uses one details-plus-videos request when a series needs both domains, while keeping
  normalization, import transactions, state, and reporting independent per domain.
- Video-only mode does not request credits, aggregate credits, external IDs, keywords,
  or availability. `refresh_content_videos.py` is a focused wrapper for that scope.
- Does not install a scheduler; orchestration remains an explicit operator command.

`analytics/scripts/ingestion/update_posters_from_tmdb_preview.py`

- Reads the processed TMDb title preview.
- Updates only `poster_url` and `backdrop_url`.
- Dry-run by default; requires `--apply` for database writes.
- Mostly useful now for refresh, repair, or new titles because current seed data already has verified poster/backdrop URLs.

`analytics/scripts/ingestion/build_tmdb_credits_preview.py`

- Builds a provider-neutral credits preview at `analytics/processed/tmdb/credits_preview.json`.
- Reads existing raw TMDb files.
- Uses TV aggregate credits for series cast when available.
- Keeps regular TV credits as fallback.
- Makes no database writes.

`analytics/scripts/ingestion/import_people_credits_from_preview.py`

- Imports `people`, `person_external_ids`, and `content_people`.
- Reads `analytics/processed/tmdb/credits_preview.json`.
- Dry-run by default; requires `--apply` for database writes.
- Reuses existing people by provider external ID and avoids duplicate relationships.

`analytics/scripts/ingestion/fetch_tmdb_person_details.py`

- Reads local `person_external_ids` where `source_name = 'tmdb'`.
- Fetches TMDb person details, including biography, profile image, birthday, and place of birth.
- Writes `analytics/processed/tmdb/person_details_preview.json`.
- Makes no database writes.

`analytics/scripts/ingestion/import_person_details_from_preview.py`

- Imports only missing safe person fields: `biography`, `profile_url`, `known_for_department`, `birthday`, and `place_of_birth`.
- Never overwrites non-empty existing values.
- Preserves place of birth as provider text and does not infer nationality.
- Dry-run by default; requires `--apply` for database writes.

`analytics/scripts/ingestion/import_content_videos_from_preview.py`

- Imports normalized TMDb video rows from the content metadata preview.
- Dry-run by default; requires `--apply` for database writes.
- Recomputes one deterministic primary video per title and removes stale TMDb rows only after a complete successful snapshot.
- Preserves video rows from other sources and records failed/empty fetch state separately.
- Uses the preview's explicit preferred-language field during apply, so preview and
  importer primary selection cannot diverge based on content original language.
- Stores the complete accepted TMDb video snapshot. The title-details API currently
  exposes only Trailer and Teaser rows; clips, featurettes, and other extras remain
  stored for possible future media features.

Analysis/reporting scripts:

- `analytics/scripts/audits/analyze_tmdb_metadata_gap.py`
- `analytics/scripts/audits/reconcile_basic_metadata.py`

These compare seed data with processed provider previews and generate reports. They do not update PostgreSQL.

## 9. Safe Database Backup / Recovery

Never drop, reset or reseed `insightstream_db` to run tests. From the repository root:

```bash
python3 backend/scripts/local_database.py backup
python3 backend/scripts/local_database.py status
```

Backups are private and outside Git. Every backup is restored into a new unique
verification database and compared before success is reported. The three-file
seed is not a backup of the enriched catalog. See `docs/backend_database_setup.md`
for checksum verification, restoration, test preparation and the implemented
migration workflow. Historical migrations are not replayed automatically.

Read-only migration commands:

```bash
python3 backend/scripts/local_database.py migrations status --target insightstream_db
python3 backend/scripts/local_database.py migrations validate --target insightstream_db
python3 backend/scripts/local_database.py migrations preview --target insightstream_db
```

The [database workflow](docs/backend_database_setup.md#migration-management-baseline-and-history)
is the command reference for creating version 016 onward, disposable migration
checks, fresh initialization and later approved development application. Baseline
registration does not execute old SQL or repair the four missing indexes.

To reverify an existing archive or compare development data with its saved baseline:

```bash
python3 backend/scripts/local_database.py restore-verify \
  --manifest "$HOME/Library/Application Support/InsightStream/backups/<run>/manifest.json"
python3 backend/scripts/local_database.py fingerprint \
  --manifest "$HOME/Library/Application Support/InsightStream/backups/<run>/manifest.json"
```

Replace `<run>` with the recorded backup directory. `restore-verify` creates a new
unique verification database; it never replaces an existing target. `status` and
`fingerprint` are read-only. Keep archives, manifests, and test credentials outside Git.

## 10. Running Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
INSIGHTSTREAM_ENV=development python3 -m uvicorn app.main:app --reload
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

From the repository root, prepare the dedicated local target once:

```bash
python3 backend/scripts/local_database.py prepare-test
python3 backend/scripts/local_database.py check-test
python3 backend/scripts/run_tests.py -q -rs
```

Pure tests can run without PostgreSQL:

```bash
python3 backend/scripts/run_tests.py --unit-only -q
```

The full runner explicitly loads private test settings outside Git. Database tests
require confirmed test mode and `TEST_DATABASE_URL`; they never fall back to the
development URL. Fixtures contain 18 deterministic titles and are reset per test,
including after real commits. Historical replay is excluded from the shared test
schema. The original two migration tests' assertions run through newly created
sandbox lifecycle checks when a private `--migration-env` is supplied; see
[migration test preparation](docs/backend_testing.md#migration-management-checks).

`prepare-test` creates only previously absent test database/role names; it refuses
unknown existing targets. To reset fixture data explicitly, first verify the target:

```bash
python3 backend/scripts/local_database.py check-test
python3 backend/scripts/local_database.py reset-test --confirm-reset insightstream_test
```

This resets only the marked disposable test database. A bare pytest invocation
without explicit test settings fails before collection. Pure tests need no database.

Frontend validation remains `cd frontend` then `npm run build`.
See [Backend Testing](docs/backend_testing.md) for safety guarantees and commands.

## 13. Current Limitations / Not Yet Implemented

- Source coverage and freshness are incomplete. The November 1 audit found 50 titles without stored IMDb ratings despite valid IDs, and 30 movies without Letterboxd ratings. Four stored Letterboxd matches required ambiguity review.
- All 429 current rating rows and 2,515 availability rows had recorded fetch/import dates over 90 days old at the audit. Provider timestamps do not prove present-day correctness.
- The availability importer inserts offers but does not reconcile disappeared offers or refresh existing rows. Series/video refresh has an explicit operator workflow, not an automatic scheduler.
- Individual reviews, review-source storage, and review-derived pros/cons/verdict generation are not implemented. The 15 legacy `content_summary` rows and 60 legacy `ratings` rows remain seeded compatibility data; current frontend ratings and insights use the newer contracts.
- Authentication and user ownership enforcement are absent; personal watch actions use a demo user. Homepage rotation is deterministic, not live trending or personalization.
- Season/episode counts are title-level metadata; there are no dedicated season/episode entities or episode-level credits. Person filmography covers only imported catalog relationships.
- Migration tracking is implemented, but development baseline registration still requires separate approval. Four declared indexes remain absent from the live database; neither baseline registration nor this milestone repairs them.
- Provider permissions, licensing, and attribution require review before public/commercial deployment. The frontend reads application APIs and does not fetch TMDb metadata directly.

## 14. Roadmap

1. **Baseline and safety — Milestone 1 complete:** preserve the 200-title catalog, verify restorable private backups, isolate PostgreSQL tests, and document reproducible local commands. Keep these checks as the foundation for later work.
2. **Data completeness and correctness:** validate existing IMDb/Letterboxd matches, fill supported aggregate-rating gaps, and distinguish missing data from intentionally unsupported review information. Check provenance before importing.
3. **Pipeline stabilization:** reconcile availability additions/removals, establish freshness checks and repeatable refresh/recovery evidence, and reduce duplicated manual ingestion steps. Do not add a scheduler before refresh behavior is reliable.
4. **Targeted architecture and schema work:** use the implemented migration checks and approval workflow, review baseline registration/index differences separately, and address demonstrated query/aggregation and maintenance problems.
5. **Controlled expansion:** require satisfactory source coverage, refresh/reconciliation, quality checks, and reproducible imports before ingesting the remaining 75 configured targets in batches 8–10 or expanding further. Ordinary tests stay independent of catalog size.
6. **Product development:** improve discovery and compact insight usability after the foundation is reliable; add authentication/ownership before shared public use. Review ingestion and richer recommendations require separate product and provider-access decisions.

The earlier 15-title metadata foundation and later ratings, recency, homepage,
video, and source-signal work remain part of the project's history. The last major
product workstream was Formatter v2.0.2 in August 2026; the November recovery work
stabilizes that implementation. Existing planning documents below retain their
historical rationale and may describe steps already delivered; this status and
roadmap reflect the verified recovery baseline.

## Documentation

### Source-signal mapping review

Run mapping work from the repository root. Review and preview commands are read-only with respect to PostgreSQL; the importer is also a dry run unless `--write` is explicitly supplied.

```bash
python3 -m analytics.scripts.source_signals.build_unmapped_keyword_review
python3 -m analytics.scripts.source_signals.build_keyword_signal_preview
python3 -m analytics.scripts.source_signals.import_source_signals_from_preview
python3 -m analytics.scripts.audits.audit_source_signal_mapping_quality
python3 -m analytics.scripts.audits.audit_decision_display_quality
python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness
```

Generated reviews, previews, dry-run reports, and audits stay under ignored `analytics/processed/` paths. Keyword identity uses the versioned `source-signal-keyword-v1` normalization contract.

The runtime mapping config is `analytics/config/source_signal_keyword_mapping.json`; tracked rationale and exact human decisions live separately in `analytics/config/source_signal_keyword_review_decisions.json`. The generated review is evidence only, not runtime configuration. Use `--baseline-mapping-file <path>` with the review command when a real before/after status comparison is required. PostgreSQL review access is explicitly read-only, and the importer remains non-mutating unless `--write` is supplied.

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
- `docs/catalog_expansion_readiness.md`

## MVP Boundary

InsightStream / CineLens is not a public social or community platform in the current MVP. User interaction is personal and utility-focused through Watch Later and Watched. Public reviews, posts, comments, followers, communities, likes, and feeds are intentionally excluded while the project focuses on structured entertainment metadata, discovery, analytics, and decision support.
