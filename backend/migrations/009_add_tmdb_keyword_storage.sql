-- ============================================================
-- InsightStream Manual Migration
-- 009_add_tmdb_keyword_storage.sql
--
-- Purpose:
-- Add normalized TMDb keyword storage tables for the raw
-- provider keyword layer. This does not create source_signals,
-- keyword-to-signal mappings, or frontend display behavior.
--
-- Safe to run more than once.
-- ============================================================

CREATE TABLE IF NOT EXISTS keyword_sources (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS provider_keywords (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES keyword_sources(id) ON DELETE CASCADE,
    external_keyword_id VARCHAR(100) NOT NULL,
    keyword_name TEXT NOT NULL,
    normalized_keyword_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_provider_keywords_source_external_keyword
        UNIQUE (source_id, external_keyword_id)
);

CREATE TABLE IF NOT EXISTS content_keywords (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    keyword_id INTEGER NOT NULL REFERENCES provider_keywords(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES keyword_sources(id) ON DELETE CASCADE,
    confidence VARCHAR(20) DEFAULT 'medium' CHECK (
        confidence IN ('low', 'medium', 'high', 'unknown')
    ),
    raw_payload JSONB,
    first_seen_at TIMESTAMP,
    last_seen_at TIMESTAMP,
    fetched_at TIMESTAMP,
    source_preview_generated_at TIMESTAMP,
    import_run_id VARCHAR(150),
    import_report_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_content_keywords_content_keyword_source
        UNIQUE (content_id, keyword_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_keyword_sources_source_name
ON keyword_sources (source_name);

CREATE INDEX IF NOT EXISTS idx_provider_keywords_source_external_keyword
ON provider_keywords (source_id, external_keyword_id);

CREATE INDEX IF NOT EXISTS idx_provider_keywords_normalized_keyword_name
ON provider_keywords (normalized_keyword_name);

CREATE INDEX IF NOT EXISTS idx_content_keywords_content_id
ON content_keywords (content_id);

CREATE INDEX IF NOT EXISTS idx_content_keywords_keyword_id
ON content_keywords (keyword_id);

CREATE INDEX IF NOT EXISTS idx_content_keywords_source_id
ON content_keywords (source_id);

CREATE INDEX IF NOT EXISTS idx_content_keywords_content_source
ON content_keywords (content_id, source_id);

INSERT INTO keyword_sources (
    source_name,
    display_name,
    is_active
)
VALUES (
    'tmdb',
    'TMDb',
    TRUE
)
ON CONFLICT (source_name) DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    is_active = EXCLUDED.is_active,
    updated_at = CURRENT_TIMESTAMP;
