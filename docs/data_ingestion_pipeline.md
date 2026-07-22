# Data Ingestion Pipeline

## 1. Purpose and Rules

This is the canonical ingestion guide for InsightStream / CineLens.

InsightStream stores normalized local data for detail pages, discovery, ratings, availability, certification, series lifecycle, people, and future source signals. The local PostgreSQL database is the app source of truth at runtime.

External providers are used through backend/offline ingestion only:

- The frontend must not call TMDb, IMDb, Letterboxd, or other provider sources directly.
- Fetch/build scripts create raw files, processed previews, and run reports.
- Import scripts must be reviewed in dry-run mode first.
- Database writes happen only through scripts that support `--apply`.
- Do not scrape websites.
- Do not import or summarize review text without an approved source/legal plan.
- Local datasets such as IMDb and Letterboxd snapshots must not be committed unless explicitly intended.
- Raw provider payloads and temporary retry artifacts should stay out of normal commits.

Future ingestion updates should go into this document.

## 2. Current Ingestion Status

| Area | Status | Main scripts | DB writes? | Notes |
| ---- | ------ | ------------ | ---------- | ----- |
| TMDb metadata/content/video fetch | Implemented | `analytics/scripts/ingestion/fetch_tmdb_sample.py` | No | Fetches/reuses TMDb raw details with appended videos, credits, external IDs, and writes `sample_mapping_preview.json`. |
| Metadata import | Implemented | `analytics/scripts/ingestion/import_content_metadata_from_preview.py` | Only with `--apply` | Imports content rows, external IDs, genres, posters/backdrops, lifecycle metadata, season summaries, latest activity dates, and safe series status refreshes. |
| TMDb video import | Implemented | `analytics/scripts/ingestion/import_content_videos_from_preview.py` | Only with `--apply` | Imports normalized video records, authoritative complete snapshots, deterministic primary selection, and per-title fetch state. |
| Poster/backdrop update behavior | Implemented | `analytics/scripts/ingestion/update_posters_from_tmdb_preview.py`, metadata importer | Only with `--apply` | Seed poster/backdrop values exist for base titles. Current scalable imports use metadata preview fields while preserving curated conflicts unless importer policy allows update. |
| Credits/people preview/import | Implemented | `analytics/scripts/ingestion/build_tmdb_credits_preview.py`, `analytics/scripts/ingestion/import_people_credits_from_preview.py` | Import only with `--apply` | Builds and imports top cast plus unified key crew into `people`, `person_external_ids`, and `content_people`. |
| Person details import | Implemented | `analytics/scripts/ingestion/fetch_tmdb_person_details.py`, `analytics/scripts/ingestion/import_person_details_from_preview.py` | Import only with `--apply` | Imports missing biography, profile, known-for department, birthday, and place-of-birth fields for local people matched by provider IDs. |
| Availability/certification import | Implemented | `analytics/scripts/ingestion/fetch_tmdb_availability_certification.py`, `analytics/scripts/ingestion/import_availability_certification_from_preview.py` | Import only with `--apply` | Imports India-focused region-aware availability and certifications. |
| Series refresh planner/fetch/import | Implemented | `analytics/scripts/refresh/plan_series_refresh.py`, `analytics/scripts/ingestion/fetch_tmdb_sample.py`, `analytics/scripts/ingestion/import_content_metadata_from_preview.py` | Planner/fetch no; import only with `--apply` | Plans refresh targets for active/recent series and refreshes dynamic lifecycle/status fields. |
| TMDb ratings import | Implemented | `analytics/scripts/ingestion/import_content_ratings_from_preview.py` | Only with `--apply` | Imports TMDb vote data from the processed metadata preview into provider-neutral ratings tables. |
| IMDb ratings import | Implemented | `analytics/scripts/ingestion/import_imdb_ratings.py` | Only with `--apply` | Uses local official IMDb non-commercial `title.ratings.tsv`; matches only through stored IMDb external IDs. |
| Letterboxd ratings preview/import | Implemented | `analytics/scripts/ingestion/preview_letterboxd_ratings_match.py`, `analytics/scripts/ingestion/import_letterboxd_ratings_from_preview.py` | Import only with `--apply` | Uses reviewed local dataset preview. Review text is ignored. Letterboxd is displayed as a dataset snapshot and excluded from InsightStream Score v1. |
| TMDb keywords preview/import | Implemented | `analytics/scripts/ingestion/build_tmdb_keywords_preview.py`, `analytics/scripts/ingestion/merge_tmdb_keywords_retry_preview.py`, `analytics/scripts/ingestion/import_tmdb_keywords_from_preview.py` | Import only with `--apply` | Fetches movie/TV keyword preview/report, supports retry/merge, and imports raw provider keywords into normalized keyword tables. |
| Keyword-to-signal preview | Implemented, preview-only | `analytics/scripts/source_signals/build_keyword_signal_preview.py` | No | Reads imported TMDb keywords from DB, applies curated mapping config, and writes local source-signal preview/report JSON only. |
| Source signal storage import | Implemented | `analytics/scripts/source_signals/import_source_signals_from_preview.py` | Only with `--write` | Imports current source signals and productized watch guidance from the clean preview into storage tables. |
| Source signal decision layer API | Implemented | `backend/app/services/source_signal_service.py`, content detail API | No | Reads stored source signals/watch guidance and returns sanitized compatibility fields plus compact `decision_layer.display` output for frontend use. |
| Homepage sections API | Implemented | `backend/app/services/content_service.py`, `GET /content/home` | No | Builds backend-powered homepage rails from local catalog data with bounded candidate pools and deterministic weekly/daily rotation. |
| Decision display QA audit | Implemented | `analytics/scripts/audits/audit_decision_display_quality.py` | No | Read-only catalog audit for compact display quality scores, issue codes, review candidates, and generated local JSON/CSV/summary reports. |
| Source signal mapping QA audit | Implemented | `analytics/scripts/audits/audit_source_signal_mapping_quality.py` | No | Read-only audit for stored signal richness, missing dimensions, generic genre/subgenre coverage, fallback dependency, and unmapped keyword opportunities. |
| Ingestion health check | Implemented | `analytics/scripts/audits/check_ingestion_health.py` | No | Read-only health checks for target coverage, metadata completeness, ratings, availability, people, and series lifecycle data. |

Not implemented yet:

- Watch Profile UI from source signals.
- Review ingestion.
- Review-derived signals.
- LLM-assisted summaries from approved stored signals.

## 3. Environment and Prerequisites

Activate the backend virtual environment before running Python scripts if dependencies are installed there:

```bash
cd backend
source .venv/bin/activate
cd ..
```

Database-aware scripts need `DATABASE_URL`:

```bash
export DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/insightstream_db
```

TMDb fetch scripts need the TMDb read token:

```bash
export TMDB_READ_ACCESS_TOKEN=YOUR_TMDB_READ_ACCESS_TOKEN
export TMDB_LANGUAGE=en-US
export TMDB_VIDEO_LANGUAGES=en,null
```

Local rating dataset paths:

```text
analytics/datasets/imdb/title.ratings.tsv
analytics/datasets/letterboxd/
```

Dataset directories are ignored by git. Do not commit downloaded IMDb or Letterboxd dataset files.

Database schema/sample/index setup belongs in `docs/backend_database_setup.md`. After the base database setup, run ingestion scripts from the repository root.

## 4. Full Metadata Setup Flow

Base database setup:

1. Run `backend/schema.sql`.
2. Run `backend/sample_data.sql`.
3. Run `backend/indexes.sql`.

Then run ingestion in this broad order:

```bash
# 1. Fetch/build TMDb content preview.
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample

# 2. Review metadata import.
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview

# 3. Apply metadata import.
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview --apply

# 4. Confirm metadata import idempotency.
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview

# 5. Review, apply, and confirm video import idempotency.
python3 -m analytics.scripts.ingestion.import_content_videos_from_preview
python3 -m analytics.scripts.ingestion.import_content_videos_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_videos_from_preview

# 6. Build and import credits/people.
python3 -m analytics.scripts.ingestion.build_tmdb_credits_preview
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview --apply
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview

# 7. Fetch and import person details.
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details
python3 -m analytics.scripts.ingestion.import_person_details_from_preview
python3 -m analytics.scripts.ingestion.import_person_details_from_preview --apply
python3 -m analytics.scripts.ingestion.import_person_details_from_preview

# 8. Fetch and import availability/certification.
python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview --apply
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview

# 9. Import ratings.
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview

python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv
python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv --apply
python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv

python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous --apply
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous

# 10. Health check.
python3 -m analytics.scripts.audits.check_ingestion_health --expect-imdb --expect-letterboxd --expect-tmdb-keywords
```

The first run of every import script should be reviewed before applying. The dry-run after apply should be clean or show only intentional unchanged rows.

## 5. TMDb Metadata and Content Pipeline

Fetch or rebuild the processed metadata preview:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample
```

Useful selection examples:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --priority batch_test_5
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --source-id 603
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --targets analytics/config/series_refresh_targets.json --refresh
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample --priority batch_test_5 --limit 5
```

The fetch script writes:

```text
analytics/processed/tmdb/sample_mapping_preview.json
analytics/processed/tmdb/run_reports/content_fetch_run_report.json
analytics/processed/tmdb/run_reports/content_video_retry_targets.json
analytics/processed/tmdb/run_reports/content_video_review_targets.json
```

Movie and TV detail requests use one source call per title:

```text
GET /movie/{tmdb_id}?append_to_response=videos&language={TMDB_LANGUAGE}&include_video_language={TMDB_VIDEO_LANGUAGES}
GET /tv/{tmdb_id}?append_to_response=videos&language={TMDB_LANGUAGE}&include_video_language={TMDB_VIDEO_LANGUAGES}
```

Authentication uses `Authorization: Bearer ...`. Tokens and authorization headers are
never written to previews or reports. Request controls are CLI-configurable:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample \
  --video-languages en,null \
  --batch-size 25 \
  --concurrency 3 \
  --request-timeout 15 \
  --max-retries 3
```

Timeouts, connection failures, HTTP 429, and HTTP 500/502/503/504 are retried with
bounded exponential backoff and jitter. `Retry-After` is respected for 429 responses.
HTTP 400/401/403/404 are not retried by default. Raw-file reuse plus per-target run
reports make interrupted runs resumable; legacy cached detail payloads without an
appended `videos` namespace are refetched when a token is available and otherwise
marked incomplete. Only automatic retry classes (transient network failures, rate
limits, and retryable provider server failures) are written to
`content_video_retry_targets.json` in the same target format accepted by the fetcher:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_sample \
  --targets analytics/processed/tmdb/run_reports/content_video_retry_targets.json \
  --refresh
```

An empty retry-target file is written after a clean run so an older failure list
cannot be mistaken for current work. Permanent provider failures, incompatible cache
without credentials, and normalization issues are written to
`content_video_review_targets.json`; that artifact is for operator review and is not
scheduled for repeated automatic retries.

Every fetched raw response has a `.meta.json` sidecar containing the source-fetch
time, request path, normalized response-affecting parameters, and a secret-free
SHA-256 request signature. Cache reuse requires a matching signature. Reusing a
matching cache preserves the original source-fetch time; preview generation does not
make old source data look freshly fetched. Legacy parameterless cache files use file
mtime with an explicit `legacy_file_mtime` origin. Parameterized legacy or incompatible
detail caches must be refetched, or fail clearly when no bearer token is available.
Sidecar `fetched_at` must be timezone-aware ISO 8601. A malformed value triggers a
refetch when credentials are available; without credentials, cache reuse falls back
conservatively to file mtime and labels the origin `legacy_file_mtime`.

`TMDB_VIDEO_LANGUAGES` and `--video-languages` accept a maximum of eight deduplicated
ISO 639-1 values plus the literal `null`. A target's original language is added when it
is already known before the detail request. The pipeline never makes a second videos
request to discover language metadata. The deterministic request order is configured
detail-language base code, known original language, configured extras, then configured
`null` fallback; lower-priority extras are dropped if the merge would exceed eight.
The detail-language base code is persisted as `videos_preferred_language` and is used
unchanged by preview and importer primary selection. Original language broadens the
source request but never silently replaces the ranking preference.

Import pattern:

```bash
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview
```

Important importer behavior:

- It matches content through provider external IDs where available.
- It preserves curated non-empty conflicts unless a field is intentionally safe to refresh.
- Dynamic series lifecycle fields can be refreshed safely.
- Existing series `content.status` can update from valid TMDb refresh previews.
- It does not blindly overwrite poster/backdrop conflicts.
- It updates `latest_activity_date` for series from valid aired dates, not future next episode/season dates.
- It stores provider-backed original title and original language when available:
  - movies use TMDb `original_title`
  - series use TMDb `original_name`
  - both use TMDb `original_language`
- The detail API/page uses original language for the language pill when present, falls back to legacy `language`, and does not infer dubbed-language availability.
- It prints affected content and series metadata titles when rows would be inserted/updated in dry-run mode, and when rows are inserted/updated with `--apply`.

### 5.1 TMDb Video Metadata

The metadata preview includes source video counts, normalized accepted records,
ignored provider records, warnings, rejection reasons, snapshot completeness,
stale-cleanup authority, retry disposition, source-fetch time, cache origin/signature,
requested/preferred languages, and the selected primary key. Accepted
fields are TMDb `key`, `site`, `type`, `name`, `official`, `iso_639_1`,
`iso_3166_1`, `published_at`, and `size`. Empty keys and structurally unsafe identities
are rejected. A malformed optional `published_at` becomes null with a warning and does
not make the snapshot incomplete. Unsupported providers with a stable site/key identity
are classified as intentionally ignored/non-playable rather than malformed; they do
not by themselves disable stale cleanup.

Storage uses:

- `content_videos` for normalized provider rows, unique by content/source/site/key;
- `content_primary_videos` for one primary selection per content item;
- `content_video_fetch_state` for success, valid-empty, failed, and incomplete state.

Run the importer from the repository root:

```bash
python3 -m analytics.scripts.ingestion.import_content_videos_from_preview
python3 -m analytics.scripts.ingestion.import_content_videos_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_videos_from_preview
```

A valid empty source snapshot and a fully normalized non-empty snapshot are
authoritative: stale TMDb rows are removed. A non-empty all-rejected snapshot is
incomplete. A mixed accepted/rejected snapshot may upsert accepted records but cannot
delete unmatched rows. Harmless duplicate source identities do not make an otherwise
complete snapshot unsafe. Failed, malformed, incomplete, count-inconsistent, or
unfingerprinted snapshots never remove existing videos. During an unsafe update the
current primary is retained while it still exists; if none exists, selection uses the
safe union of existing and accepted rows. Rows from another source are preserved.
Each title is applied in its own transaction and output names the affected
title/content/TMDb IDs. Repeated apply runs do not create duplicate rows or rewrite
unchanged video metadata.

Primary selection is deterministic and trust-first: official YouTube trailer,
official YouTube teaser, unofficial YouTube trailer, then unofficial YouTube teaser.
Within a class, preferred/neutral/other language is followed by a small preference for
the standard trailer over explicitly audio-described or sign-language variants, then
official/main/final naming, recent publication, and stable provider identity. These
accessibility variants remain accepted, stored, and available as related videos; they
remain eligible as primary when no stronger standard candidate exists, and official/type
quality still outranks this penalty. Clips, featurettes, unsupported sites, and arbitrary
row order cannot become primary.

Language is ranking metadata, not a validation requirement. Valid returned trailers
and teasers in Hindi, Korean, Japanese, Tamil, Telugu, or any other language are stored
and remain eligible. Trust/type class precedes language, so an official non-English
trailer outranks an unofficial English trailer. When candidates are otherwise equal,
the configured display/detail language wins; neutral and other returned languages are
deterministic fallbacks. Every accepted language variant remains available in `videos`.

The primary pointer is protected by a composite database foreign key, so a video from
one content item cannot be selected for another. The source-identity unique index also
serves current per-content and per-content/source lookups; redundant prefix and
status-only indexes are intentionally omitted.

Storage retains the complete accepted source snapshot, including trailers, teasers,
clips, featurettes, behind-the-scenes media, bloopers, and opening credits. The current
details API deliberately exposes only Trailer and Teaser rows through `videos`, plus
the optional `primary_video`, in one PostgreSQL-backed response. Other stored types are
reserved for possible future extras functionality and are not deleted or hidden from
the ingestion snapshot.

Within the public trailer/teaser list, primary is first, followed by official trailers,
official teasers, unofficial trailers, and unofficial teasers, then publication date
and stable source/row tie-breakers. Every returned item includes source identity,
normalized metadata, `is_primary`, `is_playable`, and safe derived URLs. A future
frontend can derive related trailers/teasers with
`videos.filter(video => !video.is_primary)` without another request. YouTube watch
URLs use `youtube.com/watch`, embeds use `youtube-nocookie.com/embed`, and both are
derived only from validated keys. No raw HTML or source payload is returned.

Fetch state stores processing-attempt time separately from the last successful source
fetch. Failed/incomplete attempts update status/error and `last_attempted_at` while
preserving the prior `last_fetched_at`. The valid-empty flag is database-constrained to
the `empty` status.

Recommended future refresh cadence (not scheduled in Phase 1): upcoming titles daily;
new releases/currently airing titles every 1-3 days; announced future seasons weekly;
older or ended titles monthly or on demand.

The title-detail frontend consumes `primary_video` for its compact hero Trailer/Teaser
action and builds the primary-first `Trailers & More` rail from the same response's
`videos` array, so it makes no second video request. A single safe video omits the
redundant rail while keeping the hero action. Playable items are revalidated against the
exact YouTube no-cookie embed host and validated source key in the browser. The single
modal iframe is mounted only after a deliberate click and unmounted on close; thumbnail
URLs use only `i.ytimg.com`. Non-playable records are omitted from the interface, while
non-English, subtitled, and accessibility-specific trailer variants remain eligible
and visible when safely playable. Other accepted source video types remain backend-only
for possible future extras support.
- Use the row-level sections such as `Would update content rows`, `Updated content rows`, and `Updated series metadata rows` to verify which titles and fields changed before and after a metadata refresh.

Processed previews are latest-run files. They are not always full-catalog snapshots. If a preview was generated with `--priority`, `--source-id`, or a target file, downstream preview builders may process only that subset.

Existing local databases created before original-title/language support should run:

```bash
psql "$DATABASE_URL" -f backend/migrations/011_add_content_original_title_language.sql
```

Existing local databases created before person birthday/place-of-birth support should run:

```bash
psql "$DATABASE_URL" -f backend/migrations/012_add_person_birthday_birthplace.sql
```

## 6. Credits and People Pipeline

Build credits preview:

```bash
python3 -m analytics.scripts.ingestion.build_tmdb_credits_preview
```

Import people and credits:

```bash
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview --apply
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview
```

Fetch person details:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details
```

Useful person detail options:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --missing-only --limit 20
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --all --limit 10
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --source-person-id 525 --refresh
python3 -m analytics.scripts.ingestion.fetch_tmdb_person_details --name "Christopher Nolan" --refresh
```

Import person details:

```bash
python3 -m analytics.scripts.ingestion.import_person_details_from_preview
python3 -m analytics.scripts.ingestion.import_person_details_from_preview --apply
python3 -m analytics.scripts.ingestion.import_person_details_from_preview
```

Person details use TMDb person fields `birthday` and `place_of_birth` when present.
Both are imported only into empty local fields; existing non-empty values are
preserved with conflict warnings. The detail API/page displays birthday and
birthplace as optional profile facts, and InsightStream does not infer
nationality from place of birth.

Safety rules:

- People are matched by `person_external_ids(source_name, external_id)`, not name alone.
- The pipeline avoids duplicate people and duplicate content-person relationships.
- Cast uses display order where available.
- Unified crew includes key crew roles such as directors, creators, writers, producers, and executive producers where provider data supports them.
- TV aggregate credits are preferred for series cast when available; regular TV credits are a fallback.
- Person detail import fills missing safe fields such as biography, profile URL, and known-for department.
- The frontend uses local backend APIs only for cast, crew, and person pages.
- Episode-level credits are out of scope.

## 7. Availability and Certification Pipeline

Fetch availability/certification preview:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification
```

Useful selection examples:

```bash
python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification --priority batch_test_5
python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification --source-id 603
python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification --all
python3 -m analytics.scripts.ingestion.fetch_tmdb_availability_certification --refresh
```

Import availability/certification:

```bash
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview --apply
python3 -m analytics.scripts.ingestion.import_availability_certification_from_preview
```

Current behavior:

- India availability is the primary display target.
- Availability is stored in region-aware rows, not inferred in the frontend.
- Supported availability types include streaming, rent, buy, ads/free where provider data maps cleanly.
- Certifications are stored with region/source information.
- Compact `content.age_rating` may be updated safely from preferred certification data.
- Missing availability is valid and should render as an empty state, not fake provider data.
- Do not fall back to US availability as if it were India availability.

## 8. Series Refresh Workflow

### Shared content refresh orchestration

The DB-backed shared planner adds video refresh readiness without replacing the
established series rules. It paginates canonical local content/TMDb identities,
keeps series and video reasons/timestamps separate, and writes ignored artifacts to
`analytics/processed/tmdb/`.

```bash
# Plan all due series/video work. No provider requests or database writes.
python3 -m analytics.scripts.refresh.run_content_refresh --plan-only --scope all

# Fetch and compare one domain without writing PostgreSQL.
python3 -m analytics.scripts.refresh.run_content_refresh --dry-run --scope series_metadata
python3 -m analytics.scripts.refresh.run_content_refresh --dry-run --scope videos

# Explicit writes. Movies receive video work only.
python3 -m analytics.scripts.refresh.run_content_refresh --apply --scope series_metadata
python3 -m analytics.scripts.refresh.run_content_refresh --apply --scope videos
python3 -m analytics.scripts.refresh.run_content_refresh --apply --scope all

# A canonical local TMDb target is forced even when not due.
python3 -m analytics.scripts.refresh.run_content_refresh --dry-run --scope all --source-id 94997

# Equivalent focused video entry point.
python3 -m analytics.scripts.refresh.refresh_content_videos --dry-run --source-id 94997
```

`--plan-only` only queries PostgreSQL and writes the ignored plan. `--dry-run` may
fetch/reuse raw TMDb details and write ignored previews/reports, but runs both existing
importers without writes. `--apply` is the only mode that writes PostgreSQL. The modes
are mutually exclusive.

Video cadence defaults are lifecycle-aware: upcoming titles daily, recent releases
and currently airing series every two days, announced future seasons weekly, and
older movies/ended series every 30 days. Valid empty snapshots use the same cadence.
Transient failures back off for one day and then two days. On the third consecutive
failure, the target and current run report move to manual review. Permanent failures
and incomplete normalization are never automatically retried; an explicit target can
still force a reviewed retry. Successful and valid-empty snapshots reset the failure
counter.
Series selection continues to call the legacy `evaluate_refresh_status` rules below
unchanged.

Apply-mode request failures are persisted in `content_video_fetch_state`: they
advance `last_attempted_at`, preserve the previous successful `last_fetched_at`, and
record a sanitized error, retryability, failure class, and consecutive failure
count. Dry runs remain write-free. Operational runs exit non-zero when any requested
domain is failed or incomplete; a valid empty video snapshot is successful and does
not fail the run.

Video-only work issues one movie/TV details request with appended videos and never
requests credits, aggregate credits, external IDs, keywords, or availability. A
series selected for both domains also uses one details-plus-videos response, then
passes that response independently through the existing series normalizer/importer
and video normalizer/importer. One domain may therefore succeed while the other is
reported incomplete or failed. Series-metadata-only work keeps the legacy appended
details request/cache shape but does not normalize, import, or update video state.
No scheduler is installed; these commands are ready
for a future external scheduler.

Generated files:

- `analytics/processed/tmdb/content_refresh_plan.json`
- `analytics/processed/tmdb/content_refresh_previews/`
- `analytics/processed/tmdb/run_reports/content_refresh_run_report.json`

The legacy workflow remains supported unchanged:

Use the series refresh planner for existing series already in the catalog:

```bash
python3 -m analytics.scripts.refresh.plan_series_refresh

python3 -m analytics.scripts.ingestion.fetch_tmdb_sample \
  --targets analytics/config/series_refresh_targets.json \
  --refresh

python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview

python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview --apply

python3 -m analytics.scripts.ingestion.import_content_metadata_from_preview

python3 -m analytics.scripts.audits.check_ingestion_health --expect-imdb --expect-letterboxd --expect-tmdb-keywords
```

Planner behavior:

- Selects series missing lifecycle metadata.
- Selects rows with null `last_refreshed_at`.
- Selects active statuses such as `ongoing`, `upcoming`, and `unknown` when stale by the refresh window.
- Selects active series when `next_episode_air_date` is within the next 14 days.
- Selects active series when a stored `next_episode_air_date` has passed and the row was last refreshed before that date.
- Selects recently aired/recently active series when stale.
- Skips ended/cancelled series by default unless `--include-ended` or `--all` is used.

Useful planner options:

```bash
python3 -m analytics.scripts.refresh.plan_series_refresh --all
python3 -m analytics.scripts.refresh.plan_series_refresh --status ongoing
python3 -m analytics.scripts.refresh.plan_series_refresh --include-ended --limit 20
```

Refresh import behavior:

- Series lifecycle metadata is series-level only.
- It does not create episode pages or season pages.
- Valid TMDb refresh previews can update existing series `content.status`.
- Season summaries distinguish released seasons from announced/upcoming seasons.
- Frontend lifecycle panels and series timing callouts depend on refreshed lifecycle metadata.

## 9. Ratings Pipeline

TMDb ratings:

```bash
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview --apply
python3 -m analytics.scripts.ingestion.import_content_ratings_from_preview
```

IMDb ratings from the official non-commercial dataset:

```bash
python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv
python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv --apply
python3 -m analytics.scripts.ingestion.import_imdb_ratings --ratings-file analytics/datasets/imdb/title.ratings.tsv
```

Letterboxd ratings from reviewed preview:

```bash
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous --apply
python3 -m analytics.scripts.ingestion.import_letterboxd_ratings_from_preview --include-ambiguous
```

Rating rules:

- TMDb ratings come from `sample_mapping_preview.json`.
- IMDb ratings use local `analytics/datasets/imdb/title.ratings.tsv`.
- IMDb matching uses stored IMDb IDs in `external_ids`, never title matching.
- Letterboxd ratings use `analytics/processed/letterboxd/letterboxd_rating_match_preview.json`.
- Letterboxd imports high-confidence rows by default and ambiguous rows only with `--include-ambiguous` after manual review.
- Letterboxd review text is ignored and not imported.
- Letterboxd is displayed as a film-community dataset snapshot.
- InsightStream Score v1 uses vote-backed scoring sources such as TMDb and IMDb; Letterboxd is excluded when vote count/weight rules exclude it.

Health check flags:

```bash
python3 -m analytics.scripts.audits.check_ingestion_health --expect-imdb
python3 -m analytics.scripts.audits.check_ingestion_health --expect-letterboxd
python3 -m analytics.scripts.audits.check_ingestion_health --expect-tmdb-keywords
python3 -m analytics.scripts.audits.check_ingestion_health --expect-imdb --expect-letterboxd --expect-tmdb-keywords
```

## 10. TMDb Keywords Preview and Import Workflow

TMDb keywords are structured provider tags for movies and TV/series. The preview and normalized raw-keyword import layers are implemented for future source-signal work.

Keyword presence is weak evidence, not proof. Missing keywords are not proof that a trait is absent. The preview workflow does not fetch reviews and does not write to the database. The importer stores raw TMDb keywords only; it does not create source signals, expose keywords through the API, or update the frontend.

### Full Preview With Retry Target Generation

```bash
python3 -m analytics.scripts.ingestion.build_tmdb_keywords_preview \
  --write-retry-targets analytics/config/tmdb_keywords_retry_targets.json
```

This fetches movie and TV/series keywords using stored TMDb IDs and writes:

```text
analytics/processed/tmdb_keywords/tmdb_keywords_preview.json
analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_report.json
```

Request retries are enabled by default. `--max-retries 2` means one initial attempt plus two retries. Transient failures include timeout, connection error, HTTP `429`, and temporary `500`/`502`/`503`/`504` responses.

### Retry Failed Titles Only

```bash
python3 -m analytics.scripts.ingestion.build_tmdb_keywords_preview \
  --target-file analytics/config/tmdb_keywords_retry_targets.json \
  --output analytics/processed/tmdb_keywords/tmdb_keywords_retry_preview.json \
  --report-output analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_retry_report.json
```

### Merge Retry Results Into Main Preview/Report

```bash
python3 -m analytics.scripts.ingestion.merge_tmdb_keywords_retry_preview \
  --main-preview analytics/processed/tmdb_keywords/tmdb_keywords_preview.json \
  --main-report analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_report.json \
  --retry-preview analytics/processed/tmdb_keywords/tmdb_keywords_retry_preview.json \
  --retry-report analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_retry_report.json \
  --retry-targets analytics/config/tmdb_keywords_retry_targets.json \
  --cleanup-temp
```

The merge helper:

- replaces failed main rows with successful retry rows by `content_id`;
- recalculates counters and keyword summaries;
- removes resolved errors;
- never deletes final main preview/report;
- removes temporary retry/backup artifacts with `--cleanup-temp` after a clean merge.

Final main keyword files:

```text
analytics/processed/tmdb_keywords/tmdb_keywords_preview.json
analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_report.json
```

Temporary retry/backup files:

```text
analytics/config/tmdb_keywords_retry_targets.json
analytics/processed/tmdb_keywords/tmdb_keywords_retry_preview.json
analytics/processed/tmdb_keywords/tmdb_keywords_preview.before_retry_merge.json
analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_retry_report.json
analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_report.before_retry_merge.json
```

After a clean merge, only the main preview/report should remain.

### Verify Final Keyword Report

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_report.json").read_text())

for key in [
    "total_titles_selected",
    "successful_fetches",
    "failed_fetches",
    "titles_with_keywords",
    "titles_with_zero_keywords",
    "total_keywords_fetched",
    "unique_keywords",
    "overall_keyword_coverage_percent",
]:
    print(f"{key}: {report.get(key)}")

print("errors:", report.get("errors"))
PY
```

Expected clean state for the current 150-title keyword preview:

```text
total_titles_selected: 150
successful_fetches: 150
failed_fetches: 0
titles_with_keywords: 150
errors: []
```

### Import Keywords From Preview

Review the keyword import dry-run first:

```bash
python3 -m analytics.scripts.ingestion.import_tmdb_keywords_from_preview
```

Apply the import only after reviewing the dry-run:

```bash
python3 -m analytics.scripts.ingestion.import_tmdb_keywords_from_preview --apply
```

Run one more dry-run after apply to confirm idempotency:

```bash
python3 -m analytics.scripts.ingestion.import_tmdb_keywords_from_preview
```

Useful batch-safe options:

```bash
python3 -m analytics.scripts.ingestion.import_tmdb_keywords_from_preview --content-type movie
python3 -m analytics.scripts.ingestion.import_tmdb_keywords_from_preview --content-id 123
python3 -m analytics.scripts.ingestion.import_tmdb_keywords_from_preview --only-content-ids-file analytics/config/some_content_ids.json
```

Importer behavior:

- upserts keyword source `tmdb`;
- upserts TMDb provider keywords by `external_keyword_id`;
- upserts content-keyword relationships by `content_id`, internal `keyword_id`, and source;
- tracks `first_seen_at`, `last_seen_at`, `fetched_at`, `source_preview_generated_at`, `import_run_id`, and `import_report_path`;
- skips failed preview rows;
- dedupes repeated keyword rows per title;
- does not delete or stale-mark missing keywords in v1;
- does not create `source_signals`;
- does not update backend API/frontend display.

The importer writes a dry-run/apply report:

```text
analytics/processed/tmdb_keywords/run_reports/tmdb_keywords_import_report.json
```

### Build Keyword-to-Signal Mapping Preview

The keyword-to-signal preview layer converts imported raw TMDb keywords into local, product-friendly watch guidance previews. It can also use local metadata fallback and curated title overrides for weak keyword-only profiles. It does not create `source_signals` tables, change backend APIs, or update the frontend.

Default preview:

```bash
python3 -m analytics.scripts.source_signals.build_keyword_signal_preview
```

Include internal keyword/evidence debug details:

```bash
python3 -m analytics.scripts.source_signals.build_keyword_signal_preview \
  --include-debug \
  --output analytics/processed/source_signals/debug/source_signal_preview_debug.json \
  --report-output analytics/processed/source_signals/debug/source_signal_preview_debug_report.json
```

Preview a small movie sample:

```bash
python3 -m analytics.scripts.source_signals.build_keyword_signal_preview \
  --content-type movie \
  --limit 20 \
  --output analytics/processed/source_signals/debug/source_signal_preview_movie_limit_20.json \
  --report-output analytics/processed/source_signals/debug/source_signal_preview_movie_limit_20_report.json
```

Partial/debug runs using `--limit`, `--content-type movie`, `--content-type series`,
`--content-id`, `--only-content-ids-file`, or `--include-debug` must pass both
`--output` and `--report-output`. This prevents local QA samples from overwriting the
full-catalog preview/report.

The preview script reads:

```text
analytics/config/source_signal_keyword_mapping.json
analytics/config/source_signal_title_overrides.json
```

It writes local-only processed outputs:

```text
analytics/processed/source_signals/source_signal_preview.json
analytics/processed/source_signals/run_reports/source_signal_preview_report.json
```

Preview behavior:

- reads imported TMDb keywords from `keyword_sources`, `provider_keywords`, and `content_keywords`;
- applies the curated keyword-to-signal mapping config, currently `2026-07-02-v3.1`;
- applies curated title overrides, currently `2026-07-02-v3.1`, for known weak or misleading keyword-only previews;
- uses local genre metadata fallback only when keyword-derived signals are weak;
- excludes noisy keywords from user-facing guidance;
- suppresses spoiler-unsafe keywords from user-facing guidance;
- generates technical signal objects plus natural `watch_guidance`;
- uses deterministic phrase rules to avoid raw-keyword phrasing such as awkward viewer labels or generic filler copy;
- reports mapping quality diagnostics such as source counts, count-plus-detail rows for fallback/override/keyword-only titles, low-signal rows, one-signal rows, bad primary identities, semantic QA rows, override candidates, and high-value unmapped candidates;
- reports `preview_generator_version` and `semantic_qa_version`, currently `2026-07-02-v3.2.1`;
- flags generic or semantically conflicting watch-feel output for curated review without failing the preview run;
- hides raw keywords unless `--include-debug` is passed;
- writes local preview/report JSON only;
- does not call TMDb, fetch reviews, scrape, write DB rows, or update frontend/API behavior.

### Import Source Signal Storage

The source-signal storage importer reads the generated preview/report and writes current source signals plus productized watch guidance into backend storage tables. It remains backend/storage only: no content-detail API field or frontend display is added by this step.

Dry-run:

```bash
python3 -m analytics.scripts.source_signals.import_source_signals_from_preview
```

Write:

```bash
python3 -m analytics.scripts.source_signals.import_source_signals_from_preview --write
```

Idempotency check:

```bash
python3 -m analytics.scripts.source_signals.import_source_signals_from_preview
python3 -m analytics.scripts.source_signals.import_source_signals_from_preview --write
```

Importer behavior:

- dry-run by default, with no DB writes;
- `--write` creates one `source_signal_import_runs` row and upserts current rows in `content_source_signals` and `content_watch_guidance`;
- imports only content IDs present in the selected preview scope;
- does not touch content IDs outside the selected preview;
- hard-deletes obsolete source signals only for selected content IDs;
- preserves mapping, override, preview-generator, and semantic-QA versions;
- blocks writes when semantic QA counts are non-zero unless `--allow-semantic-qa-issues` is passed;
- blocks partial preview writes unless `--allow-partial-preview` is passed;
- stores `storage_ready = true` and `frontend_ready = false` by default;
- writes generated import reports under `analytics/processed/source_signals/run_reports/`, which remain local-only and ignored.

### Source Signal Decision Layer API

The backend content detail response now includes a nullable `decision_layer` object when stored source-signal guidance exists. Frontend display should consume the compact `decision_layer.display` contract rather than raw source-signal internals.

The decision layer:

- reads `content_watch_guidance` and active `content_source_signals`;
- returns `display`, the preferred compact frontend-facing object with `primary_insight`, grouped profile labels, and supporting facts;
- returns a productized `watch_profile` with `watch_feel`, sanitized `chips`, `best_for`, and `consider_first`;
- returns compact `decision_support` copy with headline, reasons, and cautions;
- returns `signal_quality`, including `storage_ready`, `frontend_ready`, `has_watch_guidance`, and `has_source_signals`;
- filters or rewrites mechanical labels such as platform/viewer chips before they reach the public API;
- applies global display-quality cleanup so weak labels, identity-like themes, repeated investigation phrasing, repeated dark/intense phrasing, platform-as-identity labels, and blocked technical terms do not reach `decision_layer.display`;
- applies dominant-identity rules so stronger story forms such as prison drama, neo-noir crime thriller, historical crime drama, satirical sci-fi anthology, action-crime investigation, political-action mystery, psychological survival thriller, sci-fi mystery, and mythic superhero mystery can beat weaker labels like `Crime story`, `Assassin story`, or `Corruption story`;
- uses deterministic overview-assisted fallback cues only for compact classification, not freeform summary generation;
- fills missing compact themes from reusable context families such as historical/war drama, World War II/Holocaust/occupation context, gangster crime, heist/spy stories, investigation/conspiracy stories, space survival, political conflict, multiverse family stories, romance/disaster, and coming-of-age memory dramas;
- selects `consider_first` copy from specific signal context such as sustained tension, darker subject matter, emotional weight, eerie tone, slow-burn pacing, or dense/unusual structure instead of relying on generic caution text;
- ranks and deduplicates identity, theme, feel, pace, and `best_for` labels before building the compact profile;
- does not expose raw TMDb keywords, mapping versions, source names, or provider payloads by default;
- lets Insight Summary use stored watch guidance for richer deterministic copy while keeping metadata/rating/availability fallback behavior;
- keeps platform names in explicit Access signals rather than watch-profile identity labels.

`decision_layer.display` is the frontend-preferred contract because it avoids repeating sentence-style `watch_profile`, `decision_support`, and `insight_summary` copy across multiple UI blocks. Older `watch_profile` and `decision_support` fields remain available for backward compatibility.

Backend display examples such as sci-fi heist, political dark fantasy, kitchen workplace drama, prison drama, satirical sci-fi anthology, and psychological survival thriller are covered as regression tests for global rules. They should not be treated as title-by-title copywriting. Future catalog batches should use preview QA and API review to identify weak mapped labels, then improve shared mapping/cleanup rules before adding one-off overrides.

Preferred display shape:

```json
{
  "primary_insight": "A surreal sci-fi heist built around memory and identity, with strong audience backing.",
  "profile": {
    "identity": ["Sci-fi heist"],
    "themes": ["Memory and identity"],
    "feel": ["Surreal", "Thoughtful"],
    "pace": "Plot-driven and puzzle-like",
    "best_for": ["Heist stories", "Stories about memory and identity"],
    "consider_first": ["May feel complex on first watch."]
  },
  "supporting_facts": [
    {"label": "Audience", "value": "86/100 from 2 scoring sources"},
    {"label": "Access", "value": "Streaming in India"}
  ]
}
```

`frontend_ready` remains a data-quality flag. It is returned so the future frontend can decide whether to show, hide, or label the section, but it does not block backend/dev integration.

The legacy `summary` object may still appear in detail responses for backward compatibility. New frontend work should prefer `ratings`, `insight_summary`, `availability`, and `decision_layer.display` for decision-support UI.

### Homepage Sections API

`GET /content/home` provides the backend contract for the future homepage redesign. It is read-only and uses only local database data: catalog metadata, rating summaries, availability, source-signal labels, and stored watch guidance. It does not call external providers and does not use personalized recommendation logic yet.

The response includes a hero block and exactly these sections, in order:

1. `weekly_picks`
2. `top_rated`
3. `recent_releases`
4. `mood_pace`
5. `platform_picks`
6. `binge_worthy_series`

Refresh behavior is deterministic:

- `weekly_picks` uses ISO year/week rotation from a bounded high-quality pool.
- `top_rated`, `mood_pace`, `platform_picks`, and `binge_worthy_series` use daily deterministic rotation.
- `recent_releases` does not rotate artificially; it orders movies by release date and series by available freshness metadata such as next/last episode or last-air dates, then score/source strength, then title.

The daily and weekly seeds use the Asia/Kolkata calendar date boundary, matching the current India-focused availability region. Tests can still inject a reference date so homepage refresh behavior remains deterministic and deployment-safe.

Homepage cards are poster-led. Candidate queries for every homepage section require `poster_url` so future frontend rails do not receive posterless cards. Mood/pace buckets use positive source-signal matches plus conflict exclusions, with `light_comfort` intentionally strict so darker or intense titles do not leak into light-watch discovery. Platform buckets are curated to recognizable homepage labels such as Netflix, Prime Video, JioHotstar, Apple TV+, and YouTube when present in the local database. Standalone endpoints such as `/content/top-rated`, `/content/recent`, `/content/discover`, and `/platforms` keep their existing behavior.

The endpoint is designed for catalog growth:

- no `ORDER BY RANDOM()`;
- no full-catalog Python filtering for section selection;
- bounded candidate pools per section or bucket;
- batched card enrichment for platforms and source-signal labels;
- duplicate content IDs are prevented inside each simple section or bucket;
- existing content, rating, availability, and source-signal indexes cover the current 1,000-title target without additional schema changes.

Existing endpoints such as `/content/top-rated`, `/content/recent`, and `/content/discover` remain available. The homepage endpoint is recommendation-ready, but personalized recommendations and frontend rendering are future work.

### Decision Display Quality Audit

The decision display audit checks catalog-wide `decision_layer.display` quality using the same backend content detail service that powers the API. It is read-only and writes local-only QA reports.

Run the full catalog audit:

```bash
python3 -m analytics.scripts.audits.audit_decision_display_quality
```

Audit one title or a batch:

```bash
python3 -m analytics.scripts.audits.audit_decision_display_quality --content-id 6
python3 -m analytics.scripts.audits.audit_decision_display_quality --content-type movie --limit 50 --offset 0
```

Useful failure gates for CI-like local checks:

```bash
python3 -m analytics.scripts.audits.audit_decision_display_quality \
  --fail-on-critical \
  --fail-under-score 80
```

Generated reports:

```text
analytics/processed/source_signals/decision_display_quality_report.json
analytics/processed/source_signals/decision_display_quality_report.csv
analytics/processed/source_signals/run_reports/decision_display_quality_summary.json
```

The detailed JSON contains per-title `display_quality_score`, `grade`, `display_ready`, `review_required`, issue rows, and suggested next steps. The CSV is spreadsheet-friendly and uses pipe-separated cells for multi-value fields such as identity, themes, feel, best-for labels, and supporting facts. The summary report includes grade counts, issue counts by code/severity, weakest titles, top issue examples, and content-type breakdowns.

Scoring starts from 100 and subtracts deterministic penalties:

- critical issue: -35
- high issue: -20
- medium issue: -10
- low issue: -4

Grades:

- `excellent`: 90-100
- `good`: 80-89
- `needs_review`: 60-79
- `blocked`: below 60 or any critical issue

Use the audit to answer which titles are safe to show, which need review, which bad phrases still appear, and whether the next fix belongs in backend display rules, keyword mapping, source-signal quality, metadata enrichment, or a curated override. Regenerate the reports after backend display-rule or mapping changes to compare before/after counts. Generated audit reports remain local-only and should not be committed.

The audit casing checks allow known proper phrases and compact entertainment tokens such as `World War II`, `World War I`, `Sci-fi`, `Post-apocalyptic`, `AI`, `TV`, `PG-13`, and `TV-MA`, while still flagging awkward title-case labels such as `Historical Crime Drama`. Backend display cleanup normalizes public `best_for` labels such as `Post-apocalyptic World` into product copy like `Post-apocalyptic worlds`.

### Source Signal Mapping Quality Audit

The source signal mapping audit checks the deeper data layer behind `decision_layer.display`. It is read-only and inspects stored raw provider keywords, active source-signal dimensions, watch-guidance fallback flags, genre/subgenre enrichment opportunities, compact rating/access support context, and the current compact display output.

Run the full catalog audit:

```bash
python3 -m analytics.scripts.audits.audit_source_signal_mapping_quality
```

Audit one title or a batch:

```bash
python3 -m analytics.scripts.audits.audit_source_signal_mapping_quality --content-id 6
python3 -m analytics.scripts.audits.audit_source_signal_mapping_quality --content-type movie --limit 50 --offset 0
```

Useful failure gates for CI-like local checks:

```bash
python3 -m analytics.scripts.audits.audit_source_signal_mapping_quality \
  --fail-on-critical \
  --fail-under-score 80
```

Generated reports:

```text
analytics/processed/source_signals/source_signal_mapping_quality_report.json
analytics/processed/source_signals/source_signal_mapping_quality_report.csv
analytics/processed/source_signals/run_reports/source_signal_mapping_quality_summary.json
```

The detailed JSON contains per-title `mapping_quality_score`, `grade`, `mapping_ready`, `review_required`, signal dimensions present/missing, genre quality, fallback dependency, unmapped keyword opportunities, issue rows, and suggested next steps. The CSV is spreadsheet-friendly and uses pipe-separated cells for multi-value fields such as genres, dimensions, labels, and issue codes.

Use this audit differently from the decision display audit:

- `audit_decision_display_quality.py` answers whether the current public compact display is safe and polished enough to show.
- `audit_source_signal_mapping_quality.py` answers whether the underlying source-signal mappings are rich, specific, and scalable enough for future homepage sections, recommendations, reviews, and catalog expansion.

The mapping audit is intentionally read-only and calibrated for practical QA:

- Missing `content_caution_proxy` is currently an informational, future-facing diagnostic. Stronger intense/horror/dark-thriller contexts can still receive a meaningful caution-proxy warning.
- Backend display fallback is diagnostic unless it appears to compensate for sparse stored mappings or missing identity/theme/feel dimensions.
- Common useful labels such as `Tense`, `Suspenseful`, `Action-heavy`, `Emotional`, `Fast-paced`, `Slow-burn`, and `Darkly funny` are not treated as weak merely because they appear often.
- Genre/subgenre suggestions use stricter evidence checks, especially for war/combat labels, to avoid noisy future-work warnings.

Source Signal Mapping Improvements v1 adds reusable keyword rules for slow-burn pacing, tension/suspense mood, survival/escape themes, absurd/dark-comedy tone, war/human-cost/duty themes, space-survival sci-fi, post-apocalyptic survival, kitchen workplace drama, investigation/spy/crime expectations, AI/technology-and-society themes, and future-society/mythic sci-fi cues. It also replaces weak public labels such as `Heavier watch`, `Bleak mood`, and `Complex story` with more specific product labels.

Source Signal Mapping Improvements v2 tightens mapping-config hygiene and adds reusable rules for family/emotional character drama, coming-of-age/emotional-growth stories, workplace comedy/drama, supernatural mystery, political/crime/survival drama, historical/war context, nature documentary tone, romantic disaster drama, and mythology/identity-led superhero mystery. Config entries should keep declared `dimensions` aligned with their actual signal dimensions, avoid empty signal arrays, and avoid technical or viewer-style public labels.

Source Signal Mapping Improvements v2.1 is a targeted cleanup for the remaining weak stored-signal cases. It adds reusable period/hotel/caper, social-satire, creature-adventure, superhero-team, mythic/supernatural, brisk-investigation, action-crime, royal-power, and caper texture cues. It also tightens subgenre opportunity detection so `Kitchen workplace drama`, `Space survival sci-fi`, `Serial-killer investigation`, `Political dark fantasy`, `Mythic superhero mystery`, and war/combat candidates require concrete source evidence rather than a single vague keyword or display fallback text.

After editing `analytics/config/source_signal_keyword_mapping.json`, regenerate and verify the storage-backed quality layer:

```bash
python3 -m analytics.scripts.source_signals.build_keyword_signal_preview
python3 -m analytics.scripts.source_signals.import_source_signals_from_preview --write
python3 -m analytics.scripts.audits.check_ingestion_health --expect-imdb --expect-letterboxd --expect-tmdb-keywords --expect-source-signals
python3 -m analytics.scripts.audits.audit_source_signal_mapping_quality
python3 -m analytics.scripts.audits.audit_decision_display_quality
```

Generated mapping-quality reports remain local-only and should not be committed. Use them to prioritize mapping-config updates, genre enrichment, curated title overrides, raw keyword coverage, backend display rules, or metadata enrichment.

## 11. Output Artifact Policy

Tracked or reviewable processed artifacts depend on the repo's current data-artifact convention. In general:

- Raw TMDb files under `analytics/raw/tmdb/` are ignored.
- Local IMDb dataset files under `analytics/datasets/imdb/` are ignored.
- Local Letterboxd dataset files under `analytics/datasets/letterboxd/` are ignored.
- Temporary keyword retry target files are ignored.
- Temporary keyword retry preview/report files are ignored.
- Temporary before-retry-merge backup files are ignored.
- Source-signal preview outputs under `analytics/processed/source_signals/` are local-only.
- Final processed previews/reports may be kept locally for analysis or committed only when intentionally useful for the project state.

Ignored paths include:

```text
analytics/datasets/imdb/
analytics/datasets/letterboxd/
analytics/config/tmdb_keywords_retry_targets.json
analytics/processed/tmdb_keywords/*_retry_preview.json
analytics/processed/tmdb_keywords/*.before_retry_merge.json
analytics/processed/tmdb_keywords/run_reports/*_retry_report.json
analytics/processed/tmdb_keywords/run_reports/*.before_retry_merge.json
analytics/processed/source_signals/
```

Do not commit API keys, tokens, downloaded provider datasets, or raw review text.

## 12. Health Checks and Verification

Read-only ingestion health check:

```bash
python3 -m analytics.scripts.audits.check_ingestion_health \
  --expect-imdb \
  --expect-letterboxd \
  --expect-tmdb-keywords \
  --expect-source-signals
```

Strict mode:

```bash
python3 -m analytics.scripts.audits.check_ingestion_health \
  --strict \
  --expect-imdb \
  --expect-letterboxd \
  --expect-tmdb-keywords \
  --expect-source-signals
```

Backend tests:

```bash
cd backend
python3 -m pytest
```

Frontend build:

```bash
cd frontend
npm run build
```

Useful database spot checks:

```sql
SELECT COUNT(*) FROM content;

SELECT source_name, COUNT(*)
FROM external_ids
GROUP BY source_name
ORDER BY source_name;

SELECT rs.source_name, COUNT(*)
FROM content_ratings cr
JOIN rating_sources rs ON rs.id = cr.rating_source_id
GROUP BY rs.source_name
ORDER BY rs.source_name;

SELECT COUNT(*) FROM content_availability;
SELECT COUNT(*) FROM content_certifications;
SELECT COUNT(*) FROM people;
SELECT COUNT(*) FROM content_people;
SELECT COUNT(*) FROM provider_keywords;
SELECT COUNT(*) FROM content_keywords;
```

## 13. Current Known Keyword Findings

The current keyword preview has strong coverage across the current 150-title catalog after retry merge.

Useful repeated keywords include:

- dystopia
- suspenseful
- murder
- dark comedy
- artificial intelligence
- serial killer
- space
- detective
- survival
- investigation
- revenge
- time travel
- space opera
- murder mystery
- coming of age

Noisy or generic keywords exist and must be filtered:

- based on novel or book
- sequel
- aftercreditsstinger
- duringcreditsstinger
- woman director
- remake
- spin off

Keyword presence is weak evidence, not proof. Missing keyword is not proof of absence.

## 14. Planned Next Ingestion Tasks

These are future tasks, not implemented:

1. Review the v3 keyword-to-signal preview output and continue refining mapping/fallback/override quality.
2. Continue backend display-quality polish from stored source signals.
3. Continue frontend polish around the compact `decision_layer.display` contract.
4. Improve frontend Insight Summary presentation from source signals.
6. Later add review-derived signals after source/legal policy is clear.
7. Later add LLM-assisted summaries from approved stored signals.

## 15. Catalog Expansion Baseline

Before selecting or importing an expansion wave, run the database-only baseline:

```bash
python3 -m analytics.scripts.audits.audit_catalog_expansion_readiness
```

The audit reuses current video and series refresh decision functions but never
executes a refresh. It measures canonical metadata, raw keywords, mapped source
signals, videos/fetch state, discovery-filter coverage, and deterministic
recommendation candidate density. Reports are generated beneath the ignored
`analytics/processed/catalog_audits/` directory. See
`docs/catalog_expansion_readiness.md` for metric definitions, strict-mode
behavior, and the distinction between real-catalog performance observations and
future synthetic load testing.

Catalog and source-signal audits reuse the same versioned keyword-normalization
helper as the keyword-to-signal preview. Stored provider names, stored normalized
names, mapping keys, exclusions, and spoiler-unsafe terms therefore receive the
same punctuation and separator normalization before coverage is calculated.
