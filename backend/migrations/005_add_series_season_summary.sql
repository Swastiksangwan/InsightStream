-- ============================================================
-- InsightStream Manual Migration
-- 005_add_series_season_summary.sql
--
-- Purpose:
-- Add series-level season summary fields so detail pages can
-- distinguish released seasons from announced/upcoming seasons.
--
-- Safe to run more than once.
-- ============================================================

ALTER TABLE content_series_metadata
ADD COLUMN IF NOT EXISTS released_seasons_count INTEGER;

ALTER TABLE content_series_metadata
ADD COLUMN IF NOT EXISTS announced_seasons_count INTEGER;

ALTER TABLE content_series_metadata
ADD COLUMN IF NOT EXISTS next_season_number INTEGER;

ALTER TABLE content_series_metadata
ADD COLUMN IF NOT EXISTS next_season_air_date DATE;

ALTER TABLE content_series_metadata
ADD COLUMN IF NOT EXISTS next_season_year INTEGER;

ALTER TABLE content_series_metadata
ADD COLUMN IF NOT EXISTS has_announced_season BOOLEAN DEFAULT FALSE;

ALTER TABLE content_series_metadata
ADD COLUMN IF NOT EXISTS season_summary_note TEXT;

CREATE INDEX IF NOT EXISTS idx_content_series_metadata_has_announced_season
ON content_series_metadata (has_announced_season);

CREATE INDEX IF NOT EXISTS idx_content_series_metadata_next_season_air_date
ON content_series_metadata (next_season_air_date);
