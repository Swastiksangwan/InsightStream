# Backend Database Setup Guide

This guide explains how to set up, reset, and verify the local InsightStream backend database during development.

InsightStream currently uses PostgreSQL with SQL files stored in the repository. The database is updated only when those SQL files are executed against PostgreSQL.

## Purpose

Use this guide when you need to:

- Create the local development database tables.
- Load sample development data.
- Apply database indexes.
- Reset local development data safely.
- Verify that tables, rows, indexes, and watch-state data are present.

This guide is for local backend development only.

## Prerequisites

Before running the database setup, make sure you have:

- PostgreSQL installed and running.
- pgAdmin or `psql` available.
- A Python virtual environment ready for the backend.
- Backend dependencies installed from `backend/requirements.txt`.
- A local `backend/.env` file configured with `DATABASE_URL`.

Example local `.env` value:

```env
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db_name>
```

Do not commit `backend/.env`.

## Important Warning

Editing these files in VS Code does not automatically update PostgreSQL:

- `backend/schema.sql`
- `backend/sample_data.sql`
- `backend/indexes.sql`

These files are source-controlled setup files. To change the actual PostgreSQL database, you must execute the SQL in pgAdmin, `psql`, or another PostgreSQL client.

Recommended workflow:

1. Edit SQL files in VS Code.
2. Execute the SQL against the local database in pgAdmin or `psql`.
3. Verify the database state with SELECT queries.
4. Test backend endpoints.
5. Commit the SQL file changes only after they are verified.

## Correct Local Setup Order

For a clean local database setup, run the files in this order:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

Why this order matters:

- `schema.sql` creates the tables and constraints.
- `sample_data.sql` inserts development data into those tables.
- `indexes.sql` adds performance indexes after the tables exist.

## Run Files With pgAdmin

### 1. Open the Database

1. Open pgAdmin.
2. Connect to your local PostgreSQL server.
3. Select the InsightStream development database.
4. Open the Query Tool.

### 2. Run the Schema

1. Open `backend/schema.sql` in VS Code.
2. Copy the full file contents.
3. Paste into pgAdmin Query Tool.
4. Execute the query.

Expected result: tables are created successfully.

### 3. Run Sample Data

1. Open `backend/sample_data.sql`.
2. Copy the full file contents.
3. Paste into pgAdmin Query Tool.
4. Execute the query.

Expected result: sample rows are inserted successfully.

Current expected seed state: `backend/sample_data.sql` loads 15 content titles, split into 8 movies and 7 series.

### 4. Run Indexes

1. Open `backend/indexes.sql`.
2. Copy the full file contents.
3. Paste into pgAdmin Query Tool.
4. Execute the query.

Expected result: indexes are created successfully.

The index file uses `CREATE INDEX IF NOT EXISTS`, so it is safe to run more than once in local development.

## Optional psql Commands

From the repository root:

```bash
psql "postgresql://<user>:<password>@localhost:5432/<db_name>" -f backend/schema.sql
psql "postgresql://<user>:<password>@localhost:5432/<db_name>" -f backend/sample_data.sql
psql "postgresql://<user>:<password>@localhost:5432/<db_name>" -f backend/indexes.sql
```

If you are already connected to the database in `psql`, you can run:

```sql
\i backend/schema.sql
\i backend/sample_data.sql
\i backend/indexes.sql
```

Run these from the repository root, or adjust the file paths to match your current directory.

## Safe Local Development Reset Options

The following reset options are for local development only.

Do not run these commands on production data, shared staging data, or any database that contains important user data.

### Option A: Drop and Recreate Tables

Use this when you want a completely clean local database structure.

```sql
DROP TABLE IF EXISTS
    watch_later,
    watched,
    content_summary,
    ratings,
    external_ids,
    content_platforms,
    content_genres,
    platforms,
    genres,
    content,
    users
CASCADE;
```

Then run:

1. `backend/schema.sql`
2. `backend/sample_data.sql`
3. `backend/indexes.sql`

### Option B: Truncate Data and Reset Identities

Use this when the tables already exist and you want to clear local data while keeping the table structure.

```sql
TRUNCATE TABLE
    watch_later,
    watched,
    content_summary,
    ratings,
    external_ids,
    content_platforms,
    content_genres,
    platforms,
    genres,
    content,
    users
RESTART IDENTITY CASCADE;
```

Then run:

1. `backend/sample_data.sql`
2. `backend/indexes.sql`

This keeps the schema in place and resets generated IDs back to their starting values.

## Verification Queries

Run these queries in pgAdmin or `psql` after setup or reset.

### List Tables

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

Expected core tables:

- `content`
- `content_genres`
- `content_platforms`
- `content_summary`
- `external_ids`
- `genres`
- `platforms`
- `ratings`
- `users`
- `watch_later`
- `watched`

### Count Important Tables

```sql
SELECT 'users' AS table_name, COUNT(*) AS row_count FROM users
UNION ALL
SELECT 'content', COUNT(*) FROM content
UNION ALL
SELECT 'external_ids', COUNT(*) FROM external_ids
UNION ALL
SELECT 'genres', COUNT(*) FROM genres
UNION ALL
SELECT 'platforms', COUNT(*) FROM platforms
UNION ALL
SELECT 'content_genres', COUNT(*) FROM content_genres
UNION ALL
SELECT 'content_platforms', COUNT(*) FROM content_platforms
UNION ALL
SELECT 'ratings', COUNT(*) FROM ratings
UNION ALL
SELECT 'content_summary', COUNT(*) FROM content_summary
UNION ALL
SELECT 'watch_later', COUNT(*) FROM watch_later
UNION ALL
SELECT 'watched', COUNT(*) FROM watched;
```

### Inspect Content Rows

```sql
SELECT
    id,
    title,
    content_type,
    release_date,
    year,
    age_rating
FROM content
ORDER BY id;
```

Expected current seed count: 15 total content rows.

### Verify Content Count by Type

```sql
SELECT
    content_type,
    COUNT(*) AS total
FROM content
GROUP BY content_type
ORDER BY content_type;
```

Expected current result:

- `movie`: 8
- `series`: 7

### Verify External IDs by Source

```sql
SELECT
    source_name,
    COUNT(*) AS total
FROM external_ids
GROUP BY source_name
ORDER BY source_name;
```

Expected current result:

- `imdb`: 5
- `tmdb`: 15

### Verify Tested Title External IDs

```sql
SELECT
    c.title,
    ei.source_name,
    ei.external_id
FROM content c
JOIN external_ids ei
    ON ei.content_id = c.id
WHERE c.title IN (
    'Interstellar',
    'Inception',
    'Breaking Bad',
    'The Dark Knight',
    'Dune: Part Two'
)
ORDER BY c.title, ei.source_name;
```

Expected rows include TMDb IDs for each title and these verified IMDb IDs:

- Interstellar: `tt0816692`
- Inception: `tt1375666`
- Breaking Bad: `tt0903747`
- The Dark Knight: `tt0468569`
- Dune: Part Two: `tt15239678`

### Inspect Genres

```sql
SELECT
    id,
    name
FROM genres
ORDER BY name;
```

### Inspect Platforms

```sql
SELECT
    id,
    name,
    platform_type
FROM platforms
ORDER BY platform_type, name;
```

### Verify Indexes

```sql
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

Useful indexes to confirm include:

- `idx_content_content_type`
- `idx_content_release_date`
- `idx_content_title_lower`
- `idx_content_type_release_date`
- `idx_content_summary_unified_score`
- `idx_genres_name_lower`
- `idx_platforms_name_lower`
- `idx_content_platforms_platform_availability`
- `idx_watch_later_user_content`
- `idx_watched_user_content`

### Verify Watch Later and Watched Consistency

The backend service layer is designed to keep the same user/content pair from staying in both `watch_later` and `watched`.

Use this query to find conflicts:

```sql
SELECT
    wl.user_id,
    wl.content_id,
    c.title
FROM watch_later wl
JOIN watched w
    ON w.user_id = wl.user_id
   AND w.content_id = wl.content_id
JOIN content c
    ON c.id = wl.content_id
ORDER BY wl.user_id, wl.content_id;
```

Expected result for a clean current-state dataset: no rows.

If this query returns rows in local development, the sample or manually inserted data has conflicting watch states.

## Current Seed Data Note

`backend/sample_data.sql` is the canonical local development seed file.

The current canonical seed contains 15 titles: 8 movies and 7 series.

It is designed for the current backend state and includes sample data for:

- content listing
- content details
- top-rated discovery
- recent discovery
- genre/platform discovery
- combined discovery
- metadata endpoints
- watch later and watched examples
- provider-neutral external IDs for TMDb and verified IMDb matching

The seed file avoids hardcoded generated IDs by using stable lookups such as `tmdb_id`, genre name, platform name, and user email.

Do not use legacy/manual seed files for local setup. `backend/sample_data.sql` is the single canonical seed source.

## Recommended Future Improvements

Recommended future database setup improvements:

- Continue expanding `backend/sample_data.sql` as the single clean local seed source.
- Add more sample titles only when needed for real endpoint or frontend testing.
- Plan any future seed expansion before editing SQL.
- Optionally add database migrations later, for example with Alembic.
