# Metadata Provider Strategy

## 1. Purpose

This document defines how InsightStream should use external metadata providers without becoming permanently locked into one provider.

TMDb is the first prototype metadata provider, but it should remain replaceable. The application should depend on InsightStream's normalized schema and backend API, not on provider-specific response shapes.

## 2. Current Provider State

Current state:

- `analytics/scripts/fetch_tmdb_sample.py` exists for inspection-only TMDb sample fetching.
- `analytics/processed/tmdb/sample_mapping_preview.json` exists as a processed TMDb preview.
- `analytics/scripts/update_posters_from_tmdb_preview.py` exists for local poster/backdrop updates from the processed preview.
- 5 local PostgreSQL rows were updated for poster/backdrop validation.
- The frontend now proves provider data can flow through local DB -> backend API -> frontend.
- No full ingestion pipeline exists yet.
- No `backend/sample_data.sql` persistence decision has been finalized.
- No `external_ids` table exists yet.

## 3. Provider-Neutral Architecture Rule

Preferred architecture:

```text
External provider
-> provider fetch script
-> mapping/normalization layer
-> InsightStream database
-> FastAPI API
-> frontend
```

Rules:

- The frontend should not call TMDb directly.
- FastAPI routes should not directly depend on TMDb response shapes.
- Provider-specific logic should stay isolated in scripts or provider modules.
- Core tables should store normalized InsightStream product fields.

## 4. What Belongs in Core App Tables

Core app tables should store normalized InsightStream fields, such as:

- title
- content_type
- overview
- release_date
- year
- runtime
- language
- status
- poster_url
- backdrop_url
- genres
- ratings
- summaries
- platform availability

These should not be treated as TMDb-owned fields. TMDb is one possible source for them, not the product data model itself.

## 5. What Should Stay Provider-Specific

Provider-specific information should be isolated, such as:

- TMDb IDs
- IMDb IDs
- provider image paths
- raw payloads
- provider-specific popularity values
- provider-specific vote averages
- provider-specific credits shape

Raw provider payloads should remain local and ignored unless the project creates a clear storage policy for them.

## 6. Future External IDs Table

Plan an `external_ids` table before deeper metadata or rating-source integration.

Suggested fields:

- `id`
- `content_id`
- `source_name`
- `external_id`
- `source_url`
- `created_at`
- `updated_at`

Why this matters:

- provider replacement
- source matching
- duplicate prevention
- IMDb/OMDb/rating-source linking
- troubleshooting mismatched titles

Current `content.tmdb_id` is acceptable temporarily, but it is less flexible long term.

## 7. Future Metadata Provenance

Later, InsightStream may need to track source/provenance per field or per update.

Possible future table:

```text
content_metadata_sources
```

Possible fields:

- `content_id`
- `field_name`
- `source_name`
- `fetched_at`
- `expires_at`
- `confidence`
- `notes`

This can help with licensing/cache limits, refresh rules, and provider replacement. This is future work, not an immediate schema change.

## 8. TMDb Usage Rules For This Project

TMDb usage rules:

- TMDb is a prototype/non-commercial metadata provider for now.
- Use attribution where TMDb content is displayed.
- Do not commit API keys or tokens.
- Do not treat TMDb data as permanently owned project data.
- Do not use TMDb content for ML/AI training.
- Do not rely on frontend live access to TMDb.
- Avoid bulk ingestion until usage rights and architecture are clear.
- Public or commercial use may require a TMDb agreement or alternate source.

## 9. If TMDb Is Replaced Later

Replacement should happen behind the normalized database/API boundary.

Old flow:

```text
TMDb fetch script -> TMDb mapping -> InsightStream DB
```

New flow:

```text
Other provider fetch script -> other provider mapping -> same InsightStream DB/API
```

The frontend should still consume stable backend endpoints:

- `GET /content`
- `GET /content/{id}/details`
- discovery endpoints

This keeps the frontend and API stable even if metadata providers change.

## 10. Sample Data Persistence Decision

Current decision state:

- Local PostgreSQL has real poster/backdrop URLs for 5 titles.
- `backend/sample_data.sql` still contains placeholder-style URLs.
- If the database is reset, real URLs are lost.
- Persisting TMDb URLs into `sample_data.sql` would improve reproducibility.
- Persisting TMDb URLs also embeds provider-derived data in the repo.
- Before doing that, decide whether this is acceptable for prototype/non-commercial development and add attribution/licensing notes.

Recommendation:

Do not update `sample_data.sql` blindly. If updating seed data, do it as a controlled development seed update with clear provider/licensing notes.

## 11. Recommended Next Technical Sequence

Recommended sequence:

1. Keep TMDb scripts isolated under `analytics/scripts`.
2. Keep the frontend consuming only backend APIs.
3. Plan an `external_ids` table before rating-source integration.
4. Decide whether to persist verified poster/backdrop URLs into `sample_data.sql`.
5. Add TMDb attribution in the frontend before wider TMDb display use.
6. Later plan person/cast/crew schema.
7. Later plan ratings/scoring source strategy.
8. Later plan review/audience-thought source feasibility separately.

## 12. What Not To Do

Do not:

- make the frontend call TMDb
- hardcode TMDb assumptions throughout the backend
- store every TMDb field blindly
- build `unified_score` only from TMDb `vote_average`
- train ML/AI on TMDb content
- treat the TMDb free API as commercial infrastructure
- ignore attribution/cache/licensing concerns
- remove fallback behavior for missing provider data

## 13. Final Decision

InsightStream should use TMDb as a replaceable prototype metadata provider while building its own normalized application schema and analytics layer. The goal is not to copy a provider database, but to use allowed provider data to enrich a controlled, provider-neutral product database.
