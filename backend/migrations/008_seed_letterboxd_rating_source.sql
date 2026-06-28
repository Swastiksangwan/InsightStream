-- ============================================================
-- InsightStream Manual Migration
-- 008_seed_letterboxd_rating_source.sql
--
-- Purpose:
-- Seed Letterboxd as an active display-only audience rating
-- source for Ratings Foundation. Letterboxd ratings are
-- imported from a manually reviewed local dataset match preview.
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
    'letterboxd',
    'Letterboxd',
    'audience',
    5,
    0,
    TRUE,
    'https://letterboxd.com/',
    'Letterboxd ratings imported from a manually reviewed local dataset match preview. Vote counts are unavailable, reviews are not imported, and this source is excluded from InsightStream Score v1.'
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
