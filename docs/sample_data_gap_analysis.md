# InsightStream Sample Data Gap Analysis

## 1. Purpose

This document reviews the current canonical seed data and identifies gaps before expanding sample data or starting external data collection.

The goal is to keep future data work planned, not random. Seed data should support backend validation, frontend planning, analytics experiments, and eventual data collection without turning into scattered SQL additions.

## 2. Current Seed Data Source

`backend/sample_data.sql` is the single canonical reset-safe seed file.

`backend/updated_sample_data.sql` has been removed as legacy cleanup and should not be referenced or used.

The correct local database setup order is:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

## 3. Current Seeded Content

The current canonical seed includes four titles.

### Interstellar

- `content_type`: movie
- Release date/year: `2014-11-07` / `2014`
- Major genres: Adventure, Drama, Sci-Fi
- Platforms:
  - Prime Video: streaming
  - Apple TV+: rent
- Ratings present:
  - IMDb: general, 8.70/10, normalized 87.00
  - Rotten Tomatoes: critic, 73.00/100, normalized 73.00
  - Metacritic: critic, 74.00/100, normalized 74.00
- Summary present:
  - unified score
  - critic score
  - audience score
  - review summary
  - pros
  - cons
  - verdict

### Inception

- `content_type`: movie
- Release date/year: `2010-07-16` / `2010`
- Major genres: Action, Sci-Fi, Thriller
- Platforms:
  - Netflix: streaming
  - Prime Video: rent
- Ratings present:
  - IMDb: general, 8.80/10, normalized 88.00
  - Rotten Tomatoes: critic, 87.00/100, normalized 87.00
  - Metacritic: critic, 74.00/100, normalized 74.00
- Summary present:
  - unified score
  - critic score
  - audience score
  - review summary
  - pros
  - cons
  - verdict

### Breaking Bad

- `content_type`: series
- Release date/year: `2008-01-20` / `2008`
- Major genres: Crime, Drama, Thriller
- Platforms:
  - Prime Video: streaming
  - Netflix: streaming
- Ratings present:
  - IMDb: general, 9.50/10, normalized 95.00
  - Rotten Tomatoes: critic, 96.00/100, normalized 96.00
  - Metacritic: critic, 87.00/100, normalized 87.00
- Summary present:
  - unified score
  - critic score
  - audience score
  - review summary
  - pros
  - cons
  - verdict

### The Mandalorian

- `content_type`: series
- Release date/year: `2019-11-12` / `2019`
- Major genres: Action, Adventure, Sci-Fi
- Platforms:
  - Disney+ Hotstar: streaming
- Ratings present:
  - IMDb: general, 8.60/10, normalized 86.00
  - Rotten Tomatoes: critic, 90.00/100, normalized 90.00
  - Metacritic: critic, 70.00/100, normalized 70.00
- Summary present:
  - unified score
  - critic score
  - audience score
  - review summary
  - pros
  - cons
  - verdict

## 4. Current Data Coverage

The current sample data already supports testing:

- content listing
- content by ID
- content details
- top-rated discovery
- recent discovery
- genre discovery
- platform discovery
- combined discovery
- genre metadata
- platform metadata
- watch later
- watched
- mutual exclusivity between watch later and watched
- ratings display
- summary/pros/cons/verdict display

The seeded watch-state example uses `test@example.com`: Interstellar is watched, and The Mandalorian is in watch later.

## 5. Current Data Limitations

Current limitations:

- Too few titles for realistic discovery, pagination, ranking, or analytics testing.
- Limited content type variety: only movies and series are represented, with two examples each.
- Limited genre variety in relationships: Action, Adventure, Crime, Drama, Sci-Fi, and Thriller are used, while several seeded genres have no linked content.
- Limited platform combinations: only Netflix, Prime Video, Apple TV+, and Disney+ Hotstar are linked to content.
- Limited availability variety: streaming and rent are represented, but buy is not linked to any current title.
- Limited rating-source variety: IMDb, Rotten Tomatoes, and Metacritic are used, but all titles follow the same three-source pattern.
- Limited critic/audience/general comparison depth: seeded rating rows include critic and general reviewer groups, but no `audience` reviewer-group rows.
- Limited watch-state examples: one watched title and one watch-later title for one test user.
- No realistic trending/popularity signal yet beyond release date, rating count, and unified score.
- No cast/crew/person data yet.
- No trailers/videos/media data yet.
- No region-specific availability data yet.
- No external ingestion logs yet.

## 6. Missing Data for Better Analytics Testing

Future analytics work would benefit from:

- More movies and series.
- Mixed release years across older classics, recent releases, and current titles.
- Mixed rating levels, including excellent, average, and weaker titles.
- Critic vs audience disagreement examples.
- Different platforms and availability types, including buy examples.
- Genre overlap between titles for recommendation experiments.
- High rating count vs low rating count examples.
- Titles with missing or partial metadata for cleaning tests.
- Titles useful for recommendation testing, such as shared genres, shared platforms, and similar content types.

## 7. Suggested Seed Data Expansion Target

A practical next target is to expand sample data from the current small set to around 10-20 titles.

This should happen only after deciding a clean data format and documenting why each title is useful. The expansion should be balanced across:

- movies and series
- different genres
- different platforms
- different release years
- different rating patterns
- at least a few titles with overlapping genres
- at least a few titles available on the same platform
- at least a few titles with different critic/audience/general scores

This document should not include SQL insert statements. SQL changes should come only after a sample data expansion plan is agreed.

## 8. Data Expansion Rules

Future seed data expansion should follow these rules:

- Use stable natural-key lookups instead of hardcoded generated IDs.
- Keep `sample_data.sql` reset-safe.
- Preserve watch_later/watched mutual exclusivity.
- Avoid duplicate rating rows on repeated runs.
- Keep data readable and maintainable.
- Do not add schema changes unless required.
- Prefer realistic but manageable sample data.
- Keep `backend/sample_data.sql` as the canonical seed source.

## 9. Relationship to Analytics Plan

This gap analysis connects directly to `docs/analytics_data_collection_plan.md`.

This document identifies what the current sample data lacks. The analytics plan defines future collection, cleaning, normalization, scoring, trending, and recommendation work.

The next data task should use both documents: the analytics plan for direction and this gap analysis for the immediate seed-data needs.

## 10. Recommended Next Task

The recommended next task is to create a planned sample data expansion proposal before editing SQL.

Suggested next file:

```text
docs/sample_data_expansion_plan.md
```

That future document should decide:

- which 10-20 titles to include
- why each title is useful for testing
- what genres/platforms/ratings each title should cover
- how the expanded data will support discovery, analytics, and recommendations

## 11. Final Summary

The current canonical seed data is good for validating backend functionality, but it is still too small for strong analytics, discovery, and recommendation testing. The next step should be a planned seed expansion, not random SQL additions.
