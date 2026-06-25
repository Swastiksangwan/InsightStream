-- ============================================================
-- InsightStream Manual Migration
-- 006_add_ratings_foundation.sql
--
-- Purpose:
-- Add provider-neutral ratings tables for Ratings Foundation v1
-- and seed TMDb as the first active audience rating source.
--
-- Safe to run more than once.
-- ============================================================

CREATE TABLE IF NOT EXISTS rating_sources (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    source_category VARCHAR(50) NOT NULL CHECK (
        source_category IN ('audience', 'critic', 'theatrical', 'internal')
    ),
    raw_score_scale_default NUMERIC(8,3),
    weight NUMERIC(8,3) DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    source_url TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_ratings (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    rating_source_id INTEGER NOT NULL REFERENCES rating_sources(id) ON DELETE CASCADE,
    raw_score NUMERIC(8,3),
    raw_score_scale NUMERIC(8,3),
    normalized_score NUMERIC(5,2),
    vote_count INTEGER,
    rating_count_label TEXT,
    rating_url TEXT,
    source_payload JSONB,
    fetched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_content_ratings_content_source UNIQUE (content_id, rating_source_id),
    CONSTRAINT chk_content_ratings_normalized_score
        CHECK (normalized_score IS NULL OR (normalized_score >= 0 AND normalized_score <= 100)),
    CONSTRAINT chk_content_ratings_raw_score_scale
        CHECK (raw_score_scale IS NULL OR raw_score_scale > 0),
    CONSTRAINT chk_content_ratings_vote_count
        CHECK (vote_count IS NULL OR vote_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_content_ratings_content_id
ON content_ratings (content_id);

CREATE INDEX IF NOT EXISTS idx_content_ratings_rating_source_id
ON content_ratings (rating_source_id);

CREATE INDEX IF NOT EXISTS idx_content_ratings_source_normalized_score
ON content_ratings (rating_source_id, normalized_score);

CREATE INDEX IF NOT EXISTS idx_rating_sources_source_name
ON rating_sources (source_name);

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
    'tmdb',
    'TMDb',
    'audience',
    10,
    1.0,
    TRUE,
    'https://www.themoviedb.org/',
    'TMDb vote_average and vote_count imported through the metadata ingestion pipeline.'
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
