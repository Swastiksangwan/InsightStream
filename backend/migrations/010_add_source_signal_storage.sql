-- ============================================================
-- InsightStream Manual Migration
-- 010_add_source_signal_storage.sql
--
-- Purpose:
-- Store current keyword-derived source signals, productized watch
-- guidance, and import-run provenance. This does not expose source
-- signals through the backend API or frontend.
--
-- Safe to run more than once.
-- ============================================================

CREATE TABLE IF NOT EXISTS source_signal_import_runs (
    id BIGSERIAL PRIMARY KEY,
    run_key TEXT UNIQUE NOT NULL,
    preview_path TEXT,
    report_path TEXT,
    mapping_version TEXT,
    override_version TEXT,
    preview_generator_version TEXT,
    semantic_qa_version TEXT,
    preview_generated_at TIMESTAMPTZ,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    db_write_performed BOOLEAN NOT NULL DEFAULT FALSE,
    dry_run BOOLEAN NOT NULL DEFAULT TRUE,
    titles_seen INTEGER NOT NULL DEFAULT 0,
    titles_imported INTEGER NOT NULL DEFAULT 0,
    signals_inserted INTEGER NOT NULL DEFAULT 0,
    signals_updated INTEGER NOT NULL DEFAULT 0,
    signals_deleted INTEGER NOT NULL DEFAULT 0,
    signals_unchanged INTEGER NOT NULL DEFAULT 0,
    guidance_inserted INTEGER NOT NULL DEFAULT 0,
    guidance_updated INTEGER NOT NULL DEFAULT 0,
    guidance_unchanged INTEGER NOT NULL DEFAULT 0,
    semantic_quality_summary JSONB,
    coverage_by_content_type JSONB,
    signals_by_source JSONB,
    errors JSONB,
    warnings JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_source_signals (
    id BIGSERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    last_signal_run_id BIGINT REFERENCES source_signal_import_runs(id) ON DELETE SET NULL,
    dimension TEXT NOT NULL CHECK (
        dimension IN (
            'audience_expectation',
            'content_caution_proxy',
            'intensity',
            'mood',
            'pacing',
            'tone',
            'topic_theme'
        )
    ),
    value TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    source_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_content_source_signals_content_dimension_value
        UNIQUE (content_id, dimension, value)
);

CREATE TABLE IF NOT EXISTS content_watch_guidance (
    content_id INTEGER PRIMARY KEY REFERENCES content(id) ON DELETE CASCADE,
    last_signal_run_id BIGINT REFERENCES source_signal_import_runs(id) ON DELETE SET NULL,
    watch_feel TEXT NOT NULL,
    chips JSONB NOT NULL DEFAULT '[]'::jsonb,
    best_for JSONB NOT NULL DEFAULT '[]'::jsonb,
    consider_first JSONB NOT NULL DEFAULT '[]'::jsonb,
    keyword_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    signal_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    curated_override_applied BOOLEAN NOT NULL DEFAULT FALSE,
    metadata_fallback_applied BOOLEAN NOT NULL DEFAULT FALSE,
    storage_ready BOOLEAN NOT NULL DEFAULT TRUE,
    frontend_ready BOOLEAN NOT NULL DEFAULT FALSE,
    quality_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_signal_import_runs_run_key
ON source_signal_import_runs (run_key);

CREATE INDEX IF NOT EXISTS idx_content_source_signals_content_id
ON content_source_signals (content_id);

CREATE INDEX IF NOT EXISTS idx_content_source_signals_dimension
ON content_source_signals (dimension);

CREATE INDEX IF NOT EXISTS idx_content_source_signals_value
ON content_source_signals (value);

CREATE INDEX IF NOT EXISTS idx_content_source_signals_is_active
ON content_source_signals (is_active);

CREATE INDEX IF NOT EXISTS idx_content_source_signals_content_dimension
ON content_source_signals (content_id, dimension);

CREATE INDEX IF NOT EXISTS idx_content_watch_guidance_content_id
ON content_watch_guidance (content_id);

CREATE INDEX IF NOT EXISTS idx_content_watch_guidance_frontend_ready
ON content_watch_guidance (frontend_ready);
