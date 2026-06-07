# InsightStream Sample Data Gap Analysis

## 1. Purpose

This document reviews the current canonical seed data and identifies gaps before further expanding sample data or starting external data collection.

The goal is to keep future data work planned, not random. Seed data should support backend validation, frontend planning, analytics experiments, and eventual data collection without turning into scattered SQL additions.

Status note: this gap analysis originally reviewed the pre-expansion seed state. `backend/sample_data.sql` has since been expanded to 15 titles: 8 movies and 7 series. The original four baseline titles are still included, and the remaining gaps below still matter for future analytics, TMDb/data ingestion, and frontend testing.

## 2. Current Seed Data Source

`backend/sample_data.sql` is the single canonical reset-safe seed file.

`backend/updated_sample_data.sql` has been removed as legacy cleanup and should not be referenced or used.

The correct local database setup order is:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

## 3. Current Seeded Content

The current canonical seed includes 15 titles.

The original four baseline titles are still included and remain useful reference examples:

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
  - Rotten Tomatoes: audience, 87.00/100, normalized 87.00
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
  - Rotten Tomatoes: audience, 91.00/100, normalized 91.00
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
  - Rotten Tomatoes: audience, 97.00/100, normalized 97.00
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
  - Rotten Tomatoes: audience, 92.00/100, normalized 92.00
  - Metacritic: critic, 70.00/100, normalized 70.00
- Summary present:
  - unified score
  - critic score
  - audience score
  - review summary
  - pros
  - cons
  - verdict

Additional seeded titles added during the first expansion:

- The Dark Knight
- Parasite
- Dune: Part Two
- Barbie
- Spider-Man: Across the Spider-Verse
- Red Notice
- The Last of Us
- Stranger Things
- The Boys
- Dark
- The Witcher

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
- stronger pagination testing
- better genre and platform overlap
- audience reviewer-group display
- streaming/rent/buy availability examples

The seeded watch-state example uses `test@example.com`: Interstellar and Inception are watched, while The Mandalorian and Dune: Part Two are in watch later.

## 5. Current Data Limitations

Current limitations after the first seed expansion:

- Title count has improved to 15, but it is still small for realistic analytics, recommendations, and frontend stress testing.
- Genre variety and overlap have improved, but they are still manually curated.
- Platform combinations have improved, including Netflix, Prime Video, Disney+ Hotstar, JioCinema, and Apple TV+.
- Availability variety now includes streaming, rent, and buy examples.
- Audience reviewer-group rows were added, but all ratings are still plausible development data rather than API-collected data.
- Watch-state examples are still intentionally small and limited to one test user.
- No real external ingestion exists yet.
- No true trending/popularity metrics table exists yet.
- No cast/crew/person data yet.
- No trailers/videos/media data yet.
- No region-specific availability data yet.
- No external ingestion logs yet.
- No automated analytics scripts exist yet.

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

The first practical expansion target has been completed: `backend/sample_data.sql` now contains 15 titles.

Future expansion should happen only after deciding what additional testing or analytics need it serves. Any future growth beyond 15 titles should remain balanced across:

- movies and series
- different genres
- different platforms
- different release years
- different rating patterns
- at least a few titles with overlapping genres
- at least a few titles available on the same platform
- at least a few titles with different critic/audience/general scores

This document should not include SQL insert statements. Future SQL changes should come only after a data need or expansion plan is agreed.

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

This document identifies what the current sample data still lacks. The analytics plan defines future collection, cleaning, normalization, scoring, trending, and recommendation work.

The next data task should use both documents: the analytics plan for direction and this gap analysis for the remaining seed-data and ingestion needs.

## 10. Recommended Next Task

The original recommended next task was to create a planned sample data expansion proposal before editing SQL. That task has been completed.

The follow-up planning document is:

```text
docs/sample_data_expansion_plan.md
```

That document decided:

- which 15 titles to include
- why each title is useful for testing
- what genres/platforms/ratings each title should cover
- how the expanded data will support discovery, analytics, and recommendations

Recommended next tasks now include backend endpoint tests, frontend integration planning, analytics script planning, or future TMDb ingestion design.

## 11. Final Summary

The current canonical seed data is now strong enough for validating backend functionality, discovery, pagination, and early frontend planning. It is still too small for mature analytics, real trending, and recommendation testing. The next step should be planned tests, frontend integration planning, analytics scripts, or ingestion design rather than random SQL additions.
