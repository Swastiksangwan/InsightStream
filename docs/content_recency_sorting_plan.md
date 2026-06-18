# Content Recency Sorting Plan

## 1. Purpose

Movie and series recency are not the same thing. For movies, `release_date` usually works as the date that makes a title feel new in a catalog. For series, `release_date` currently represents the original premiere or first air date, which can be years before the latest season or episode.

`release_date` should remain the original release, first air date, or first premiere date. It is useful for detail pages, year display, historical ordering, and source comparison. It should not be overwritten with a latest season or latest episode date just to make sorting feel fresher.

For Recent sorting, series need a separate latest activity signal. A series should rank by the most recent meaningful show activity when that value is available, while still preserving its original premiere date for display.

## 2. Current Problem

Before the `latest_activity_date` implementation, backend sorting used `content.release_date` for Recent ordering:

- `GET /content/recent` orders by `c.release_date DESC, c.title ASC`.
- Discovery with `sort_by=recent` also orders by `c.release_date DESC, c.title ASC`.
- The homepage Recent Releases section reads from `GET /content/recent`.

This works reasonably for movies because the movie release date is the main recency date.

For series, `release_date` represents `first_air_date` or first season premiere date. That means an actively updated series can look old if it first premiered years ago. A show with a recent season or recently aired episode should be able to rank as recent without changing its original release date.

Implementation status: `content.latest_activity_date` has been added to support Recent sorting while preserving `release_date` as the original release or first air date.

## 3. Recommended Fields

Recommended current fields:

- `release_date`: original movie release date or series first air date.
- `latest_activity_date`: normalized date used for Recent sorting.

Optional future fields:

- `first_air_date`: explicit series first air date if the project later wants to separate it from movie release date.
- `last_air_date`: latest known aired episode date for a series.
- `latest_season_air_date`: latest season premiere date for a series.
- `next_air_date`: next scheduled episode date when useful.
- `season_count`: current number of seasons.

For the MVP, add only `latest_activity_date` unless a broader season/episode model is needed immediately. This keeps the change focused, avoids premature season schema, and fixes the misleading Recent sort.

## 4. Sorting Logic

Recommended Recent ordering:

```sql
ORDER BY COALESCE(latest_activity_date, release_date) DESC, title ASC
```

Movies:

- `latest_activity_date` can equal `release_date`.
- Alternatively, movie `latest_activity_date` can stay `NULL` and rely on the `release_date` fallback.
- The simpler seed/data-import rule is to set movie `latest_activity_date = release_date` when importing or seeding.

Series:

Set `latest_activity_date` from the best available normalized source:

1. `last_episode_to_air.air_date`, if available.
2. `last_air_date`, if available.
3. Latest valid `seasons[].air_date`, if available.
4. `release_date` fallback.

If a provider supplies future dates, the import should flag them for review. A future "Upcoming" or "Returning" experience may use `next_air_date`, but the first Recent implementation should focus on latest known aired activity.

## 5. Display Logic

Detail pages should continue to show the original year derived from `release_date`. A series that premiered in 2019 should not look like it originally released in 2025 just because it has a newer season.

Recommended display behavior:

- Cards and detail hero can keep showing the existing `year` from `release_date`.
- Recent sorting can use `latest_activity_date` internally without changing visible year text.
- Later, series cards may optionally show a secondary label such as `Latest: 2025` or `Latest activity: May 2025`.
- Do not show latest activity as the primary release year.

This preserves historical accuracy while making Recent sorting more useful.

## 6. TMDb Mapping Notes

TMDb movie details provide `release_date`, which maps cleanly to the current `release_date`.

TMDb TV list/search/discover payloads commonly provide `first_air_date`, which should continue to map to the original series `release_date` or a future `first_air_date` field.

TMDb TV details/raw payloads should be inspected for:

- `last_air_date`
- `last_episode_to_air.air_date`
- `next_episode_to_air.air_date`
- `seasons[].air_date`

The current local raw TV details already show that these fields can be available. For example, the raw TV details payloads include `last_air_date`, `last_episode_to_air`, and season air dates for seeded series.

Provider fields must be normalized into app-owned fields. The application should not depend directly on TMDb field names in route handlers or frontend components.

## 7. Required Implementation Changes Later

Recommended implementation sequence:

1. Update `backend/schema.sql` to add `latest_activity_date DATE` to `content`.
2. Update `backend/sample_data.sql` to seed `latest_activity_date` for the current 15 titles.
3. Update `analytics/scripts/fetch_tmdb_sample.py` and processed preview mapping so series produce a normalized `latest_activity_date`.
4. Update backend Recent sorting:
   - `GET /content/recent`
   - discovery `sort_by=recent`
   - any genre/platform result ordering that is intended to mean recency
5. Use `ORDER BY COALESCE(c.latest_activity_date, c.release_date) DESC, c.title ASC`.
6. Decide whether API responses should expose `latest_activity_date`.
   - If it remains sort-only, no frontend type change is needed.
   - If cards/detail pages display a `Latest:` label, update backend schemas and frontend types.
7. Add backend tests for mixed movie/series recent sorting behavior.
8. Update `docs/backend_database_setup.md` with the new column and verification query.

If `latest_activity_date` is exposed later, update:

- `backend/app/schemas/content.py`
- `backend/app/services/content_service.py`
- `frontend/types/content.ts`
- any card/detail UI that displays latest activity.

## 8. What Not To Do

Do not:

- overwrite `release_date` for series with a latest season date.
- make series look like they originally released in the latest season year.
- call TMDb from the frontend.
- hardcode misleading years in the frontend.
- mix this with ratings, reviews, or unified score changes.
- build broad season/episode schema before the MVP recency need requires it.
- use provider-specific TMDb field names directly in API responses.

## 9. Recommended Next Task

After this plan, implement `latest_activity_date` as a focused schema and sorting update:

1. Add `content.latest_activity_date`.
2. Seed current movies with their release date or leave them `NULL` with fallback.
3. Seed current series from reviewed latest TV activity dates.
4. Update Recent sorting to use `COALESCE(latest_activity_date, release_date)`.
5. Add tests proving active series rank correctly without changing their original `release_date` or `year`.

The goal is to make Recent sorting useful while preserving clean metadata semantics: `release_date` means original release or premiere, and `latest_activity_date` means the date used for catalog recency.
