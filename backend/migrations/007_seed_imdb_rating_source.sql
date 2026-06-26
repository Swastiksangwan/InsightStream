-- ============================================================
-- InsightStream Manual Migration
-- 007_seed_imdb_rating_source.sql
--
-- Purpose:
-- Seed IMDb as an active audience rating source for Ratings v2.
-- IMDb ratings are imported from the official non-commercial
-- title.ratings.tsv dataset, not scraped from IMDb webpages.
--
-- Safe to run more than once.
-- ============================================================

INSERT INTO rating_sources (
    source_name,
    display_name,
    source_category,
    raw_score_scale_default,
    weight,
    is_active,
    source_url,
    notes
)
VALUES (
    'imdb',
    'IMDb',
    'audience',
    10,
    1.0,
    TRUE,
    'https://developer.imdb.com/non-commercial-datasets/',
    'IMDb ratings imported from the official non-commercial title.ratings.tsv dataset.'
)
ON CONFLICT (source_name) DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    source_category = EXCLUDED.source_category,
    raw_score_scale_default = EXCLUDED.raw_score_scale_default,
    weight = EXCLUDED.weight,
    is_active = EXCLUDED.is_active,
    source_url = EXCLUDED.source_url,
    notes = EXCLUDED.notes,
    updated_at = CURRENT_TIMESTAMP;
