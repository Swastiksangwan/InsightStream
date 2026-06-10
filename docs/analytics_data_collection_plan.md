# InsightStream Analytics and Data Collection Plan

## 1. Purpose

This document defines how InsightStream will collect, organize, clean, analyze, and use entertainment data for the film/series MVP.

Analytics is a core part of InsightStream. It is what separates the project from a simple CRUD/watchlist app. The long-term goal is not only to store content rows, but to turn entertainment data into useful decision-support signals such as normalized ratings, unified scores, summaries, verdicts, trending signals, and recommendations.

## 2. Current Product Direction Reminder

InsightStream is an information-first entertainment decision-support platform.

The MVP focuses on film/series decision support. It should help users understand what is trending, what is worth watching, where content is available, and how it is rated across different sources.

The MVP does not include public user reviews, posts, comments, communities, social feeds, or public discussion systems. User interaction should remain personal and utility-focused, such as watch later and watched.

The basic backend/frontend MVP loop is now connected, and frontend polish pass 1 is complete. The next major phase should focus on data collection and analytics planning rather than adding random new product surfaces.

## 3. Data Needed for the MVP

### Content Metadata

The MVP needs structured metadata for each movie or series:

- title
- content type
- overview
- release date
- year
- runtime
- language
- status
- age rating
- poster/backdrop images
- real poster/backdrop URLs suitable for frontend display
- TMDb ID or other external IDs

### Genre Data

The MVP needs genre metadata and relationships:

- genre names
- content-genre relationships

### Platform Availability Data

The MVP needs availability data so users can understand where content can be watched:

- OTT/platform name
- availability type: streaming/rent/buy
- region support later if needed

### Ratings Data

The MVP needs ratings from multiple sources:

- rating source
- original score
- original scale
- normalized score
- rating count
- reviewer group: critic/audience/general

### Summary / Decision-Support Data

The MVP needs simplified decision-support fields:

- unified score
- critic score
- audience score
- review summary
- pros
- cons
- verdict

Current frontend note: the content detail page v1 already displays these backend summary fields and scores. Deeper analytics scripts, real external data collection, and automated score generation are still future work.

Future detail-page data needs also include richer labels, director, cast, crew, and person relationships. These should be planned before changing the schema/API.

### User Action Data

The MVP needs personal user activity data:

- watched
- watch later
- later possible favorites/private ratings/private notes

## 4. Possible Data Sources

Possible data sources for future phases include:

- TMDb API for movie/series metadata, posters, release dates, descriptions, genres, cast/crew later, and videos later.
- OMDb API or similar sources for IMDb-style ratings if used later.
- Manually curated sample data for local development.
- Review/rating sources where allowed by API access, terms, and data usage rules.
- Internal calculated fields such as `unified_score` and verdict.

Data source usage should respect API terms, rate limits, attribution requirements, and allowed data usage. No external integration should be added until the source, fields, and usage limits are understood.

Near-term source planning should prioritize real poster/backdrop URLs, rating-source selection, metadata quality, richer labels, and whether person/cast/crew data can be ingested cleanly.

Metadata provider strategy:

- TMDb is the first prototype metadata provider.
- The backend should stay provider-neutral where possible.
- Do not tightly couple InsightStream's schema or API responses to TMDb-only response shapes.
- Store source names and external IDs where useful.
- Keep TMDb replaceable if licensing, commercial direction, or product needs change.

Licensing and data independence notes:

- TMDb is acceptable for prototype/non-commercial development with attribution.
- Public or commercial use may require a separate written agreement with TMDb.
- Do not assume TMDb content can be cached or stored forever.
- Do not use TMDb content for ML/AI training.
- Do not commit API keys.
- Building InsightStream's own database means building a normalized schema and analytics layer, not permanently copying provider data without rights.
- Long-term options include commercial agreements, licensed sources, open/permissive datasets, and curated or owned data.

## 5. Data Collection Approach

### Phase 1: Manual/Seed Data

Use `backend/sample_data.sql` for local backend testing. This file is the canonical reset-safe seed source for the current backend state.

Manual seed data should stay small, readable, and useful for endpoint testing. It should support content listing, details, discovery, metadata endpoints, ratings, summaries, and watch-state examples.

### Phase 2: Script-Based Data Collection

Later, create scripts under `analytics/scripts/` or carefully scoped backend utility scripts to fetch metadata from APIs.

These scripts should be separate from FastAPI route logic. API routes should serve application data; collection scripts should gather and prepare data.

### Phase 3: Cleaning and Normalization

Clean inconsistent names, dates, scores, missing values, and duplicate content.

Examples:

- normalize title casing where needed
- standardize release dates
- handle missing runtime or age rating
- deduplicate content by external IDs
- normalize rating scales to a shared score range

### Phase 4: Database Ingestion

Insert cleaned data into PostgreSQL tables.

Ingestion should preserve existing table responsibilities:

- content metadata into `content`
- genres into `genres` and `content_genres`
- platform availability into `platforms` and `content_platforms`
- source ratings into `ratings`
- decision-support outputs into `content_summary`

### Phase 5: Analytics Outputs

Generate analytics outputs that improve decision support:

- normalized ratings
- unified scores
- review summaries
- trending signals
- recommendation inputs
- richer content labels and detail-page analytics fields

These outputs should be explainable enough that the product can show users why something is worth watching.

## 6. Rating Normalization Plan

Different sources use different rating scales, such as:

- 10-point scale
- 5-star scale
- 100-point scale
- percentage scale

All ratings should be converted to a 0-100 scale.

Example conversions:

- 8.6/10 -> 86
- 4.2/5 -> 84
- 91/100 -> 91
- 93% -> 93

The current `ratings` table already includes `normalized_score`, so future collection and cleaning logic should calculate and store normalized values consistently.

## 7. Unified Score Plan

`unified_score` should combine ratings into a single decision-support score.

For now, a simple future approach can be:

- `critic_score` from critic sources
- `audience_score` from audience sources
- `general_score` from general sources
- `unified_score` as a weighted average

Placeholder formula:

```text
unified_score = (critic_score * 0.4) + (audience_score * 0.4) + (general_score * 0.2)
```

This formula is not final. It should be adjusted later based on available data quality, source reliability, rating counts, and whether audience/general data is consistently available.

## 8. Review Summary and Verdict Plan

InsightStream should summarize review signals without allowing public user reviews in the MVP.

Allowed:

- external review summaries
- platform-generated summaries
- stored pros/cons/verdict
- later NLP/sentiment summarization if data is legally available

Not included:

- public user review submission
- public comments
- community review feeds

The product can present summarized review insight while staying an information-first decision-support platform.

## 9. Trending and Popularity Plan

Possible future trending/popularity signals include:

- recent release date
- high rating count
- high unified score
- recent popularity from external APIs
- watch later activity
- watched activity
- manually curated trending sample data during early development

The current backend already has top-rated and recent discovery endpoints. True trending logic can be added later after data collection improves and the project has clearer popularity signals.

## 10. Recommendation Foundation

Recommendation logic can start simple.

Possible v1 recommendation signals:

- same genres
- same content type
- same platform availability
- high unified score
- not already watched
- related to watch later/watched history later

Recommendation work should happen after the data foundation is clearer. The first version should be understandable, testable, and based on existing database fields before introducing heavier ML approaches.

## 11. Current Database Support

The current database already supports the MVP analytics foundation through these tables:

- `content`
- `genres`
- `content_genres`
- `platforms`
- `content_platforms`
- `ratings`
- `content_summary`
- `watched`
- `watch_later`

These tables are enough for the current MVP analytics foundation. They support structured content information, genre/platform browsing, rating comparison, score summaries, and personal watch-state signals.

## 12. Future Schema Enhancements

Possible future schema additions include:

- `external_ids` table
- cast/crew/person tables
- videos/trailers table
- popularity/trending metrics table
- recommendation results table
- user preferences table
- favorites/custom collections tables
- ingestion logs table

These should not be added until the need is proven. The current schema should remain stable while the MVP, analytics workflow, and frontend are still being clarified.

## 13. Analytics Folder Role

The `analytics/` folder should eventually contain:

- raw datasets
- processed datasets
- cleaning scripts
- normalization scripts
- scoring scripts
- recommendation experiments
- notebooks or reports if needed

Analytics scripts should be added gradually and should not be mixed randomly with backend route logic. Backend routes should expose product APIs; analytics scripts should collect, clean, transform, and prepare data.

## 14. Immediate Next Analytics Tasks

Small practical next tasks:

1. Decide the first external data source, likely TMDb for metadata and real poster/backdrop URLs.
2. Define rating-source strategy before adding more rating data.
3. Define the first unified score calculation approach.
4. Define the review summary/verdict strategy.
5. Plan richer labels beyond only `movie` and `series`, such as anime, short film, documentary, miniseries, and special.
6. Plan director/cast/crew/person ingestion and schema/API needs before implementation.
7. Create small collection, cleaning, normalization, and scoring scripts only after the data mapping is clear.

## 15. Final Direction

InsightStream's next major direction should balance backend stability, analytics/data collection, and frontend integration. The project should not keep expanding backend APIs randomly. The analytics layer should now become a planned part of the product so the platform can provide real decision-support value.
