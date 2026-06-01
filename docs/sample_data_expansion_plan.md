# InsightStream Sample Data Expansion Plan

## 1. Purpose

This document plans the next seed data expansion before editing `backend/sample_data.sql`.

The goal is to improve testing for discovery, analytics, frontend planning, and future recommendations without randomly adding SQL rows. The expansion should be deliberate, readable, and connected to the current MVP direction.

## 2. Current Decision: Seed Expansion Before TMDb Ingestion

The immediate next step is to expand planned seed data to around 10–20 titles.

Full TMDb/API ingestion should come later. TMDb will be useful, but it requires API key handling, field mapping, duplicate handling, rate-limit awareness, and ingestion design.

For now, seed data can be manually curated. It should still stay compatible with future TMDb IDs and metadata so the project can move from manual seed data to API-backed ingestion later without rethinking the whole structure.

## 3. Current Seed Baseline

The current canonical seed in `backend/sample_data.sql` includes four titles:

- Interstellar
- Inception
- Breaking Bad
- The Mandalorian

This baseline already tests:

- movies and series
- genres
- platforms
- ratings
- summaries
- watch later/watched examples
- discovery endpoints

## 4. Expansion Goals

The expanded sample data should support:

- better pagination testing
- better discovery testing
- genre overlap
- platform overlap
- content type balance
- recent vs older content
- strong vs average ratings
- critic/audience/general rating variation
- recommendation experiments
- future frontend cards and detail pages

## 5. Recommended Dataset Size

The first expansion should target around 12–16 titles, not the full 20 immediately.

This size is enough for useful testing while still being readable and maintainable. It is easier to verify manually, keeps SQL review manageable, and reduces the risk of messy seed data.

After the first expansion is verified in pgAdmin and Swagger, the dataset can grow to 20+ titles if needed.

## 6. Title Selection Criteria

Seed titles should be selected using these rules:

- Include both movies and series.
- Include different release years.
- Include multiple genres.
- Include overlapping genres.
- Include multiple platforms.
- Include streaming/rent/buy availability.
- Include high, medium, and lower rating examples.
- Include at least some critic vs audience difference.
- Include some recent/pop-culture-relevant titles.
- Avoid adding too many titles from one franchise or one genre.

## 7. Proposed Title Categories

### Existing Baseline Titles

These should remain because they already validate the current backend surface and provide continuity for existing manual testing.

### Additional Popular Movies

Popular movies help test content cards, detail pages, high-recognition search results, cross-platform ratings, and top-rated sorting.

### Additional Popular Series

Series help keep the dataset balanced and make content type filtering meaningful.

### Recent/Pop-Culture Titles

Recent or culturally visible titles help test recent discovery, homepage sections, and future trending-style behavior.

### Lower/Average-Rated Comparison Titles

Not every title should be highly rated. Average or mixed-reception examples are useful for sorting, verdict language, and recommendation quality.

### Recommendation-Testing Titles

Titles with overlapping genres, platforms, or rating patterns help test future recommendation logic without needing machine learning immediately.

## 8. Proposed Titles

The following set keeps the planned expansion around 15 total titles, including the existing four.

### 1. Interstellar

- `content_type`: movie
- Why useful: Existing baseline title for details, Sci-Fi discovery, ratings, and watched state.
- Suggested genre coverage: Adventure, Drama, Sci-Fi
- Suggested platform coverage: Prime Video streaming, Apple TV+ rent
- Suggested rating pattern: Existing high general score with critic scores and stored summary.

### 2. Inception

- `content_type`: movie
- Why useful: Existing baseline title for Action/Sci-Fi overlap and movie discovery.
- Suggested genre coverage: Action, Sci-Fi, Thriller
- Suggested platform coverage: Netflix streaming, Prime Video rent
- Suggested rating pattern: Existing high general score and strong critic comparison.

### 3. Breaking Bad

- `content_type`: series
- Why useful: Existing high-rated series baseline for top-rated sorting and watched/history testing later.
- Suggested genre coverage: Crime, Drama, Thriller
- Suggested platform coverage: Netflix and Prime Video streaming
- Suggested rating pattern: Existing very high rating pattern.

### 4. The Mandalorian

- `content_type`: series
- Why useful: Existing series baseline and watch-later example.
- Suggested genre coverage: Action, Adventure, Sci-Fi
- Suggested platform coverage: Disney+ Hotstar streaming
- Suggested rating pattern: Existing strong but varied critic/general pattern.

### 5. The Dark Knight

- `content_type`: movie
- Why useful: Useful for high-rated action/crime testing and top-rated movie sorting.
- Suggested genre coverage: Action, Crime, Drama, Thriller
- Suggested platform coverage: Prime Video or Apple TV+ rent/buy in seed data
- Suggested rating pattern: High critic/high audience style example.

### 6. Parasite

- `content_type`: movie
- Why useful: Useful for drama/thriller testing and international/non-blockbuster variety.
- Suggested genre coverage: Drama, Thriller
- Suggested platform coverage: Prime Video rent/buy or another available seed platform
- Suggested rating pattern: High critic/high audience style example.

### 7. Dune: Part Two

- `content_type`: movie
- Why useful: Useful for recent/pop-culture discovery and Sci-Fi/Adventure overlap.
- Suggested genre coverage: Adventure, Drama, Sci-Fi
- Suggested platform coverage: Apple TV+ rent/buy or Prime Video rent in seed data
- Suggested rating pattern: Recent highly rated blockbuster pattern.

### 8. Barbie

- `content_type`: movie
- Why useful: Useful for recent/pop-culture discovery and genre variety beyond action/Sci-Fi.
- Suggested genre coverage: Comedy, Fantasy, Adventure
- Suggested platform coverage: Prime Video rent/buy or another available seed platform
- Suggested rating pattern: Strong popularity with possible critic/audience difference.

### 9. Spider-Man: Across the Spider-Verse

- `content_type`: movie
- Why useful: Useful for Animation coverage, younger-audience appeal, and high visual/media card testing.
- Suggested genre coverage: Animation, Action, Adventure, Sci-Fi
- Suggested platform coverage: Netflix streaming or Prime Video rent in seed data
- Suggested rating pattern: High critic/high audience style example.

### 10. Red Notice

- `content_type`: movie
- Why useful: Useful as a lower/average-rated comparison title so the dataset is not only highly rated.
- Suggested genre coverage: Action, Comedy, Crime
- Suggested platform coverage: Netflix streaming
- Suggested rating pattern: Average or mixed reception pattern with useful critic/audience contrast.

### 11. The Last of Us

- `content_type`: series
- Why useful: Useful for recent/pop-culture series testing and drama/thriller discovery.
- Suggested genre coverage: Drama, Thriller, Horror
- Suggested platform coverage: JioCinema streaming or another seed platform
- Suggested rating pattern: Strong critic and audience pattern.

### 12. Stranger Things

- `content_type`: series
- Why useful: Useful for popular series testing, Sci-Fi/Horror overlap, and recommendation experiments.
- Suggested genre coverage: Drama, Fantasy, Horror, Sci-Fi
- Suggested platform coverage: Netflix streaming
- Suggested rating pattern: Strong audience/general popularity pattern.

### 13. The Boys

- `content_type`: series
- Why useful: Useful for mature action/comedy series testing and platform filtering.
- Suggested genre coverage: Action, Comedy, Crime, Drama
- Suggested platform coverage: Prime Video streaming
- Suggested rating pattern: Strong audience/general pattern with critic comparison.

### 14. Dark

- `content_type`: series
- Why useful: Useful for Mystery/Sci-Fi/Thriller overlap and recommendation testing for complex series.
- Suggested genre coverage: Crime, Drama, Mystery, Sci-Fi, Thriller
- Suggested platform coverage: Netflix streaming
- Suggested rating pattern: High audience/general pattern.

### 15. The Witcher

- `content_type`: series
- Why useful: Useful for Fantasy/Adventure coverage and mixed reception testing.
- Suggested genre coverage: Action, Adventure, Drama, Fantasy
- Suggested platform coverage: Netflix streaming
- Suggested rating pattern: Mixed critic/audience pattern useful for comparison.

## 9. Data Fields Needed Per Title

Before editing SQL, prepare these fields for each title:

- `tmdb_id`
- `title`
- `content_type`
- `overview`
- `poster_url`
- `backdrop_url`
- `release_date`
- `year`
- `runtime`
- `language`
- `status`
- `age_rating`
- genres
- platforms
- `availability_type`
- ratings
- `original_score`
- `original_scale`
- `normalized_score`
- `rating_count`
- `reviewer_group`
- `unified_score`
- `critic_score`
- `audience_score`
- `review_summary`
- `pros`
- `cons`
- `verdict`

## 10. Rating and Summary Rules

`normalized_score` should use the 0–100 scale.

Each title should preferably have multiple rating rows. Future expansion should add at least some `audience` reviewer-group rows if possible, because the current seed mostly uses critic and general reviewer groups.

`content_summary` should have realistic `unified_score`, `critic_score`, `audience_score`, `review_summary`, `pros`, `cons`, and `verdict`.

Ratings should be useful for testing sorting and comparison. They do not need to be perfect real-world data at this stage, but they should be plausible, consistent, and easy to reason about.

Until ratings are collected from external APIs, manually seeded ratings should be treated as plausible development data, not authoritative production data.

## 11. Platform and Availability Rules

Use multiple OTT platforms from the existing platform seed set.

The expanded seed should include:

- streaming examples
- rent examples
- buy examples

Some titles should share platforms so platform filtering is meaningful. Avoid every title having the exact same platform pattern.

Platform availability in seed data is for local development and API testing. It does not need to represent real-time availability exactly, because real provider availability can vary by region and change over time. When TMDb or another provider API is added later, availability data should be refreshed from the selected source.

## 12. Watch-State Sample Rules

Keep one test user for now unless there is a clear testing need for more.

Preserve mutual exclusivity between `watch_later` and `watched`.

Add a few watched and watch-later examples only if useful for frontend and API testing. Do not put the same user/content pair in both tables.

## 13. SQL Update Rules for Later

The later SQL update should follow these rules:

- Use stable natural-key lookups.
- Do not hardcode generated IDs.
- Keep `backend/sample_data.sql` reset-safe.
- Avoid duplicate ratings on repeated runs.
- Keep SQL readable.
- Do not create schema changes unless required.
- Keep `backend/sample_data.sql` the single canonical seed file.

## 14. Recommended Next Task After This Plan

After this document is reviewed manually, the next task should be:

```text
Update backend/sample_data.sql based on this expansion plan.
```

The SQL update should happen only after the title list, data fields, platform patterns, and rating/summary patterns are approved.

## 15. Final Summary

The next data step is not full TMDb ingestion yet. The correct next step is a controlled seed-data expansion plan, followed by a careful update to `backend/sample_data.sql`. TMDb ingestion should come later after the sample format, mapping rules, and analytics needs are clearer.
