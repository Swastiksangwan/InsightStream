# Data Ingestion and Scoring Roadmap

## 1. Purpose

This document defines the next major backend, data, and analytics direction after the basic InsightStream frontend/backend MVP loop.

The goal is to move from plausible seeded development data toward real, structured, explainable entertainment data. The current app already proves the product loop: users can browse, discover, open detail pages, compare scores and summaries, and manage personal Watch Later/Watched state. The next phase should improve the quality and trustworthiness of the data behind that experience.

## 2. Current State

Current project state:

- Backend APIs are stable.
- Frontend MVP loop v1 is connected.
- Canonical seed data has 15 titles.
- Poster and backdrop URLs are placeholder-style development values.
- Ratings, summaries, unified scores, pros, cons, and verdicts are plausible development data.
- No external ingestion pipeline exists yet.
- No person, cast, crew, or director schema exists yet.
- No automated scoring or summarization pipeline exists yet.

The current schema supports content metadata, genres, platform availability, ratings, content summaries, and personal watch-state tables. It does not yet support ingestion logs, source attribution, media records, richer labels, person data, or scoring metadata.

## 3. Immediate Data Priorities

Highest-priority data improvements:

1. Real poster/backdrop URLs
2. Stable external IDs such as TMDb IDs
3. More reliable metadata
4. Rating source strategy
5. Unified score calculation plan
6. Review summary/pros/cons/verdict generation plan
7. Richer content labels beyond movie/series
8. Director/cast/crew/person data planning
9. Clickable genre/person navigation support later

These priorities should be planned before adding broad new UI surfaces or large datasets.

## 4. External Data Source Strategy

Possible data sources:

- TMDb for movie/series metadata, posters, backdrops, genres, cast/crew, videos, popularity, and external IDs.
- OMDb or a similar source for IMDb-style ratings if appropriate.
- Other rating or review sources only if API access and terms allow the needed usage.
- Manually curated seed data for local development and predictable testing.

Important source rules:

- Respect API terms.
- Respect attribution requirements.
- Respect rate limits.
- Avoid scraping unless legally and technically allowed.
- Avoid storing restricted data if terms do not allow it.
- Design ingestion and field mapping before coding scripts.

InsightStream should avoid treating every source as interchangeable. Metadata, ratings, reviews, popularity, and availability can have different source quality, usage permissions, and update frequency.

Metadata provider strategy:

- Treat TMDb as the first prototype metadata provider, not a permanent hard dependency.
- Keep the backend data model provider-neutral where practical.
- Do not tightly couple application tables or API responses to TMDb-only response shapes.
- Store source names and external IDs where useful so providers can be compared or replaced later.
- Keep TMDb replaceable if licensing, attribution, commercial direction, or product needs change.

Licensing and long-term data independence notes:

- TMDb can be used for prototype/non-commercial development with attribution.
- Public or commercial use may require a separate written agreement with TMDb.
- Do not assume TMDb content can be cached or stored forever without checking rights.
- Do not use TMDb content for ML/AI training.
- Do not commit API keys.
- Building InsightStream's own database means building a normalized schema and analytics layer; it does not mean permanently copying provider data without rights.
- Long-term options include commercial agreements, licensed sources, open/permissive datasets, and curated or owned data.

## 5. TMDb First Use Case

TMDb is the practical first source to evaluate because it can support:

- real poster URLs
- backdrop URLs
- overview
- release date
- runtime
- genres
- TMDb IDs
- cast/crew later
- popularity/vote data later

The first TMDb task should not ingest thousands of titles. Start with a small controlled script for either:

- the current 15 seeded titles, or
- 3-5 known test titles

The first output should be saved and inspected before anything is inserted into PostgreSQL. This keeps the mapping visible and avoids silently polluting the database with fields that do not fit the current schema.

## 6. Real Poster/Backdrop Plan

The current frontend already has fallback poster and backdrop handling, which should remain in place. Real poster/backdrop data will still make the homepage, discovery page, saved pages, and detail pages look much more realistic.

Planning decisions:

- Decide whether `content.poster_url` and `content.backdrop_url` should store full image URLs or provider image paths.
- Store image data consistently.
- Avoid hardcoding fake image paths in long-term seed data.
- Keep fallback UI for missing images, broken images, or unavailable provider data.
- Consider a future media/images table only if multiple image sizes, providers, or image types become necessary.

For an early TMDb phase, the simplest path may be to store full resolved image URLs in the current `poster_url` and `backdrop_url` fields, then revisit a media table later if the image model becomes more complex.

## 7. Rating Source Strategy

InsightStream should keep rating data grouped by signal type:

- `general`
- `critic`
- `audience`

Potential future sources:

- IMDb-style general rating
- Rotten Tomatoes-style critic/audience signal if legally available
- Metacritic-style critic rating if available
- TMDb vote average as a possible popularity/general signal, not as the only quality score

Rating-source considerations:

- Not all sources are equivalent.
- `rating_count` matters because a score with more votes may be more reliable.
- Source reliability matters.
- Source availability may differ by content type.
- Some sources may be useful for display only, while others may be useful in scoring.

Before expanding rating ingestion, define which sources are allowed, how they map to `reviewer_group`, and whether they can be stored or only displayed.

## 8. Unified Score Strategy

The current `unified_score` is seeded development data. It is useful for sorting, UI testing, and validating the detail page, but it is not the final production score.

A future unified score should consider:

- critic score
- audience score
- general score
- source reliability
- rating count/confidence
- missing data
- recency or popularity only if justified

Placeholder approach, not final:

```text
unified_score = weighted score based on critic, audience, and general rating signals
```

The final formula should be tested after real data is collected. The score should also be explainable on the detail page later, especially when data is missing, sparse, or source coverage is uneven.

## 9. Review Summary / Pros / Cons / Verdict Strategy

Possible phases:

### Phase 1: Manual Summaries

Use manually curated summaries for seed data and local development. These should be clearly treated as development content, not authoritative external consensus.

### Phase 2: Source-Backed Summaries

Use source-backed summaries only where API access and legal terms allow it. Any displayed summary should be traceable internally to its source or generation method.

### Phase 3: NLP/Sentiment Summarization

Use NLP or sentiment summarization only if legally usable review text is available. Do not collect or process restricted review text.

Important boundaries:

- Do not allow public user-submitted reviews in the MVP.
- Do not fabricate summaries as real external consensus.
- Track whether summaries are manual, generated, or source-backed.

## 10. Richer Content Labels

The current `content_type` is broad:

- `movie`
- `series`

Future classification may need:

- anime
- short film
- documentary
- miniseries
- special
- limited series
- live event later if the product expands

Recommended direction:

- Keep `content_type` broad if it continues to be useful.
- Add tags, categories, or labels for finer classification.
- Avoid breaking existing frontend/backend API contracts.
- Plan schema/API changes before implementation.

For example, anime may be better represented as a label/category while the broad `content_type` remains `movie` or `series`.

## 11. Director, Cast, Crew, and Person Data

Director, cast, crew, and person data are important future detail-page features.

Future backend support may need:

- `persons` table
- `content_person_roles` table
- `role_type`: director, actor, writer, creator, showrunner
- `character_name` for actors
- `display_order` for cast/crew
- `profile_image` path/url
- person detail page API later
- content details API extended to include director/cast/crew

Frontend rules:

- Do not fake person data.
- Director should eventually appear on the content detail page.
- Person entries should eventually be clickable.
- Person pages should come only after the backend can provide stable person identity and role data.

## 12. Clickable Genre and Person Navigation

Future navigation plan:

- Genre chips on the detail page should eventually link to filtered discovery/listing.
- A near-term route could be `/discover?genre=Sci-Fi`.
- The discovery page may need URL query param support.
- Person links should come later after person schema/API exists.

This is frontend + backend coordination work. Genre navigation can likely happen earlier because genres already exist in the current schema/API. Person navigation should wait until person identity, roles, and person detail endpoints are designed.

## 13. Suggested Backend Schema/API Enhancements Later

Possible future additions:

- `external_ids` table
- `persons` table
- `content_person_roles` table
- `media` or `images` table if needed
- `ingestion_jobs` table
- `rating_source_config` table
- `analytics_outputs` or scoring metadata table if needed
- `content_labels` or `content_tags` tables if needed
- recommendations/similar content endpoint later

These are future enhancements, not immediate changes. The next step is mapping and planning, not random schema expansion.

## 14. Suggested Phased Implementation Plan

### Phase 1: Data Source Decision and Field Mapping

Decide TMDb fields, rating sources, image handling, and mapping to the current schema.

### Phase 2: Small TMDb Fetch Script

Fetch metadata for 3-5 known titles and save raw JSON locally for inspection.

### Phase 3: Poster/Backdrop Update Path

Decide how to update the current seed or local database with real image paths.

### Phase 4: Rating/Scoring Prototype

Prototype normalized score and unified score logic using available data.

### Phase 5: Schema Expansion Planning

Plan external IDs, person/cast/crew, labels, and ingestion logs.

### Phase 6: API Expansion

Extend the details API only after schema/data is ready.

### Phase 7: Frontend Display Expansion

Update the detail page to show director, cast/crew, richer labels, analytics explanations, and clickable navigation.

## 15. What Not To Do Yet

Do not:

- ingest huge datasets yet
- implement full TMDb ingestion immediately
- add schema changes randomly
- fake cast/crew data in the frontend
- finalize the unified score formula before real data review
- assume provider data can be cached or stored forever
- use TMDb content for ML/AI training
- couple the app permanently to TMDb-only response shapes
- add public reviews/posts/comments/social feed

The next phase should be controlled and inspectable. Small, verified data steps are more valuable than a large ingestion pipeline that is hard to validate.

## 16. Recommended Next Task

Recommended next concrete task:

Create a TMDb field mapping plan for the current schema.

Suggested file:

```text
docs/tmdb_field_mapping_plan.md
```

That document should decide:

- which TMDb fields map to current `content` fields
- which fields cannot be stored yet
- whether to store full image URLs or image paths
- how to handle genres
- how to handle external IDs
- what schema gaps exist before cast/crew ingestion

## 17. Final Summary

The next major InsightStream phase should move from manually seeded demo data toward real, explainable, source-aware entertainment data. The current MVP loop works, but the product's long-term value depends on reliable ingestion, real media assets, rating-source strategy, unified scoring, review summarization, richer labels, and person/cast/crew support.
