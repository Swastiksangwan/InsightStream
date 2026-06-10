# TMDb Field Mapping and Schema Gap Plan

## 1. Purpose

This document maps useful TMDb data to the current InsightStream backend schema and identifies schema/API gaps before writing ingestion scripts.

The goal is to make content detail pages richer and more useful without randomly changing the schema or forcing data into the wrong fields. TMDb can improve metadata and media quality, but InsightStream should only ingest fields that have a clear storage model, product purpose, and API path.

TMDb should be treated as the first prototype metadata provider, not a permanent hard dependency. The backend should remain provider-neutral where possible, store source names/external IDs where useful, and avoid coupling core application data to TMDb-only response shapes.

Licensing note: TMDb can be used for prototype/non-commercial development with attribution, but public or commercial use may require a separate written agreement with TMDb. Do not assume TMDb content can be cached or stored forever, do not use TMDb content for ML/AI training, and do not commit API keys.

## 2. Current Backend Data Model

Current relevant tables from `backend/schema.sql`:

- `content`: stores broad movie/series metadata, including `tmdb_id`, `title`, `content_type`, `overview`, `poster_url`, `backdrop_url`, `release_date`, `year`, `runtime`, `language`, `status`, and `age_rating`.
- `genres`: stores unique genre names.
- `content_genres`: links content rows to genres.
- `platforms`: stores OTT platforms and rating/review sources.
- `content_platforms`: stores content availability by platform and availability type.
- `ratings`: stores source ratings, original scales, normalized scores, rating counts, and reviewer groups.
- `content_summary`: stores decision-support scores, review summary, pros, cons, and verdict.
- `watched`: stores personal watched state.
- `watch_later`: stores personal watch-later state.

The current `content` table supports broad movie/series metadata, but it does not yet model full TMDb person, media, keyword, production, network, certification, or external ID structures.

## 3. TMDb Data Categories to Consider

Useful TMDb data categories:

- movie details
- TV details
- posters/backdrops/images
- genres
- credits/cast/crew
- external IDs
- videos/trailers
- keywords
- production companies
- networks
- popularity/vote data
- release dates/certifications if available
- alternative titles if useful later

Not all of these should be ingested immediately. The first phase should focus on fields that either fit the current schema or expose a clear schema gap.

## 4. Fields That Fit Current Schema

| TMDb Field | Movie/TV Source | Current InsightStream Field/Table | Notes |
| --- | --- | --- | --- |
| `id` | movie details / TV details | `content.tmdb_id` | Direct mapping. Keep unique. Verify seeded IDs before relying on them. |
| `title` | movie details | `content.title` | Direct movie title mapping. |
| `name` | TV details | `content.title` | Direct series title mapping. |
| `overview` | movie details / TV details | `content.overview` | Direct mapping when present. |
| `release_date` | movie details | `content.release_date` | Direct movie date mapping. |
| `first_air_date` | TV details | `content.release_date` | Approximate series date mapping. Represents first air date, not every season. |
| Year derived from `release_date` or `first_air_date` | movie details / TV details | `content.year` | Derived field. Should be calculated during ingestion. |
| `runtime` | movie details | `content.runtime` | Direct movie runtime mapping. |
| `episode_run_time` | TV details | `content.runtime` | Approximate series runtime. Use first or representative value only after deciding a rule. |
| `original_language` | movie details / TV details | `content.language` | Approximate mapping. Current seed uses readable language names; TMDb returns language codes. Decide whether to store codes or translated names. |
| `status` | movie details / TV details | `content.status` | Direct mapping, but TV status values may differ from movie values. |
| `poster_path` | movie details / TV details | `content.poster_url` | Direct only after resolving full image URL, or store path if that decision changes later. |
| `backdrop_path` | movie details / TV details | `content.backdrop_url` | Direct only after resolving full image URL, or store path if that decision changes later. |
| `genres[].name` | movie details / TV details | `genres.name` + `content_genres` | Direct relationship mapping. Use natural-key lookup by genre name. |
| `vote_average` | movie details / TV details | possible `ratings` row or future scoring input | Approximate/future. Should not automatically become the unified score. |
| `vote_count` | movie details / TV details | possible `ratings.rating_count` or confidence input | Approximate/future. Useful for confidence and popularity context. |
| `popularity` | movie details / TV details | future popularity/trending input | Future-only. Current schema has no popularity metric table. |

The current API exposes `poster_url` as `poster` and `backdrop_url` as `backdrop`, so improving those two fields will immediately improve homepage, discovery, saved pages, and detail-page visuals.

## 5. Poster and Backdrop Mapping Decision

TMDb returns image paths such as `poster_path` and `backdrop_path`. Full image URLs require:

- a base URL
- an image size
- the file path

Early implementation can store full resolved image URLs in `content.poster_url` and `content.backdrop_url` for simplicity. A later implementation could instead store provider image paths and resolve size/base URL in the backend or frontend.

First project decision:

For the first controlled TMDb phase, store full resolved TMDb image URLs in the existing `poster_url` and `backdrop_url` fields.

This keeps the current API response shape stable and lets the existing frontend render real media without schema changes. Keep the fallback UI for missing, broken, or unavailable images.

This decision can be revisited later if a `media` or `images` table is added.

## 6. Fields That Need Schema Expansion

| TMDb Data | Why Useful | Suggested Future Storage | Priority |
| --- | --- | --- | --- |
| External IDs such as IMDb ID | Source linking, rating-source matching, duplicate prevention | `external_ids` table | High |
| Credits cast | Detail-page cast section | `persons` + `content_person_roles` | High |
| Crew/director | Detail-page director and crew sections | `persons` + `content_person_roles` | High |
| Videos/trailers | Detail-page media/trailer section | `media` or `videos` table | Medium |
| Keywords | Richer labels and recommendations | `content_tags` or `content_keywords` table | Medium |
| Production companies | Detail-page metadata and source context | `production_companies` table, or simpler text/JSON later | Medium |
| TV networks | Series metadata | `networks` table or later platform-style relation | Medium |
| Alternative titles | Search and disambiguation | `alternative_titles` table | Low/Medium |
| Images beyond primary poster/backdrop | Richer media support | `media` or `images` table | Low/Medium |

These should be planned before implementation. Avoid adding broad tables without clear API and frontend usage.

## 7. Movie vs Series Mapping Differences

Movie and TV data are similar but not identical:

- Movies use `title` and `release_date`.
- TV uses `name` and `first_air_date`.
- Movie runtime is usually `runtime`.
- TV runtime may use an `episode_run_time` array.
- TV has creators, networks, seasons, and episodes.
- Series status may differ from movie status.
- Director may be clearer for movies, while creator/showrunner may be more important for series.

The current schema can store both as `content` rows with `content_type` values of `movie` or `series`. Deeper TV fields need later schema/API design instead of being squeezed into generic text fields.

## 8. Content Labels and Categories

Current `content_type` is broad:

- `movie`
- `series`

TMDb may not directly solve all future labels, such as:

- anime
- short film
- documentary
- miniseries
- special
- limited series

Plan:

- Keep `content_type` broad for now.
- Later add labels, tags, or categories for finer classification.
- Do not break current frontend filters.
- Use TMDb genres, keywords, origin country, production info, runtime, episode counts, or curated rules carefully if labels are derived later.

Example: anime may remain `content_type = series` or `content_type = movie`, with an added `anime` label later.

## 9. Ratings and TMDb Vote Data

TMDb `vote_average` and `vote_count` can be useful, but they should not become the only quality score.

Potential mapping:

- `vote_average` can become a `ratings` row with `reviewer_group = general` only if the project decides that TMDb votes are acceptable as a displayed rating source.
- `vote_count` can map to `ratings.rating_count` or feed future scoring confidence.
- `popularity` can feed future trending logic, not necessarily quality.
- Final `unified_score` should wait until multiple rating sources are reviewed.

TMDb should be treated as metadata-first for the initial phase. Rating-source strategy should be handled in a separate ratings/scoring task.

## 10. Cast, Crew, Director, and Person Mapping

Director, cast, crew, and person data are important future detail-page data.

Future mapping:

- TMDb person `id` -> `persons.external_tmdb_person_id` or a generic `external_ids` relationship.
- Person `name` -> `persons.name`.
- `profile_path` -> `persons.profile_image_url` or stored provider path.
- Cast `character` -> `content_person_roles.character_name`.
- Cast `order` -> `content_person_roles.display_order`.
- Crew `job` and `department` -> `content_person_roles.role_type`, `job`, and/or `department`.
- Director -> `role_type = director`.
- Writer/creator/showrunner -> role fields.

Do not ingest cast/crew into the current schema until person tables are designed. The frontend should not fake person data before the backend can provide stable person identities and role relationships.

## 11. External IDs Strategy

External IDs matter because they support:

- matching IMDb/OMDb/rating sources later
- avoiding duplicates
- source attribution
- future imports
- troubleshooting mismatched content

Current support:

- `content.tmdb_id` exists and is useful for TMDb-backed content.

Future `external_ids` table should support:

- `content_id`
- `source_name`
- `external_id`
- `source_url` if useful

Priority:

High before rating-source integration.

External IDs should also help keep providers replaceable. TMDb IDs are useful, but future ingestion should be able to store alternate IDs from licensed sources, open datasets, or curated internal data.

## 12. First TMDb Fetch Script Output

The first script should be created later, not in this task.

First script should:

- read a small list of known TMDb IDs or titles
- fetch movie/TV details
- fetch poster/backdrop paths
- fetch genres
- fetch external IDs if simple
- optionally fetch credits for inspection only
- save raw JSON to a local ignored folder or `analytics/raw/`
- print a concise mapped preview

Do not insert into PostgreSQL in the first script. The first goal is inspection and field mapping confidence.

## 13. Suggested First 3-5 Test Titles

Use current seeded titles for the first TMDb mapping:

- Interstellar
- Inception
- Breaking Bad
- The Mandalorian
- Dune: Part Two

Use known TMDb IDs from `backend/sample_data.sql` where available. Verify IDs before relying on them, especially for older placeholder-like IDs.

## 14. Current Schema Gap Summary

Already supported:

- basic metadata
- genres
- poster/backdrop fields
- ratings table
- content summary
- platform availability
- watch states

Needs expansion:

- external IDs
- person/cast/crew/director
- videos/trailers
- richer labels/tags
- ingestion logs
- rating source config
- scoring metadata/source attribution
- real image/media model if needed

## 15. Recommended Implementation Sequence

1. Create TMDb field mapping plan. This document.
2. Create a small TMDb fetch script for 3-5 titles.
3. Inspect raw JSON and mapped preview.
4. Update poster/backdrop fields using the current schema if mapping is clear.
5. Plan an `external_ids` table.
6. Plan person/cast/crew schema.
7. Extend the details API only after schema support exists.
8. Update the detail page for director/cast/crew/person.
9. Plan rating-source and unified-score pipeline separately.

## 16. What Not To Do Yet

Do not:

- ingest thousands of titles
- store every TMDb field blindly
- add person/cast/crew UI without backend data
- finalize unified score from TMDb `vote_average` alone
- mix ingestion logic into FastAPI route handlers
- commit API keys
- scrape review sites
- assume TMDb content can be cached or stored forever
- use TMDb content for ML/AI training
- make TMDb the only possible metadata provider in the application design

TMDb ingestion should start small and inspectable. The first useful outcome is confidence in field mapping, not database volume.

## 17. Final Decision

The first TMDb phase should focus on controlled metadata and media mapping, especially real poster/backdrop URLs and reliable content metadata. Cast/crew/person, external IDs, richer labels, and rating-source integration are important, but they require planned schema/API support before implementation. Long term, InsightStream should build its own normalized schema and analytics layer while keeping metadata providers replaceable and legally usable.
