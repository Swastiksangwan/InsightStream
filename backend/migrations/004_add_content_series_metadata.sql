-- ============================================================
-- InsightStream Manual Migration
-- 004_add_content_series_metadata.sql
--
-- Purpose:
-- Add series-level lifecycle metadata support for content detail
-- pages and ingestion refreshes.
--
-- Safe to run more than once.
-- ============================================================

CREATE TABLE IF NOT EXISTS content_series_metadata (
    content_id INTEGER PRIMARY KEY REFERENCES content(id) ON DELETE CASCADE,
    number_of_seasons INTEGER,
    number_of_episodes INTEGER,
    series_status TEXT,
    series_status_normalized TEXT,
    in_production BOOLEAN,
    first_air_date DATE,
    last_air_date DATE,
    last_episode_air_date DATE,
    next_episode_air_date DATE,
    series_type TEXT,
    source_name TEXT DEFAULT 'tmdb',
    last_refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_content_series_metadata_status_normalized
ON content_series_metadata (series_status_normalized);

CREATE INDEX IF NOT EXISTS idx_content_series_metadata_last_air_date
ON content_series_metadata (last_air_date);

CREATE INDEX IF NOT EXISTS idx_content_series_metadata_next_episode_air_date
ON content_series_metadata (next_episode_air_date);
