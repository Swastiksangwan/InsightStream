CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE content (
    id SERIAL PRIMARY KEY,
    tmdb_id INTEGER UNIQUE,
    title VARCHAR(255) NOT NULL,
    original_title TEXT,
    content_type VARCHAR(20) NOT NULL CHECK (content_type IN ('movie', 'series')),
    overview TEXT,
    poster_url TEXT,
    backdrop_url TEXT,
    release_date DATE,
    latest_activity_date DATE,
    year INTEGER,
    runtime INTEGER,
    language VARCHAR(50),
    original_language VARCHAR(16),
    status VARCHAR(50),
    age_rating VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS external_ids (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    source_name VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_external_ids_content_source UNIQUE (content_id, source_name),
    CONSTRAINT uq_external_ids_source_external_id UNIQUE (source_name, external_id)
);

CREATE TABLE IF NOT EXISTS people (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    profile_url TEXT,
    known_for_department VARCHAR(100),
    biography TEXT,
    birthday DATE,
    place_of_birth TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS person_external_ids (
    id SERIAL PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    source_name VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_person_external_ids_person_source UNIQUE (person_id, source_name),
    CONSTRAINT uq_person_external_ids_source_external_id UNIQUE (source_name, external_id)
);

CREATE TABLE IF NOT EXISTS content_people (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    role_type VARCHAR(30) NOT NULL CHECK (role_type IN ('cast', 'director', 'creator', 'crew')),
    character_name VARCHAR(255),
    job VARCHAR(150),
    department VARCHAR(150),
    display_order INTEGER,
    source_name VARCHAR(50),
    source_credit_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE genres (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE content_genres (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL,
    genre_id INTEGER NOT NULL,
    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE,
    FOREIGN KEY (genre_id) REFERENCES genres(id) ON DELETE CASCADE,
    UNIQUE (content_id, genre_id)
);

CREATE TABLE platforms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    platform_type VARCHAR(30) NOT NULL CHECK (platform_type IN ('ott', 'rating_source', 'review_source'))
);

CREATE TABLE content_platforms (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL,
    platform_id INTEGER NOT NULL,
    availability_type VARCHAR(20) NOT NULL CHECK (availability_type IN ('streaming', 'rent', 'buy')),
    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE,
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE,
    UNIQUE (content_id, platform_id, availability_type)
);

CREATE TABLE IF NOT EXISTS content_availability (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    platform_id INTEGER NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
    availability_type VARCHAR(50) NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    source_name VARCHAR(50) NOT NULL,
    source_provider_id VARCHAR(100),
    display_priority INTEGER,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_content_availability_content_platform_type_region_source
        UNIQUE (content_id, platform_id, availability_type, region_code, source_name)
);

CREATE TABLE IF NOT EXISTS content_certifications (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    certification VARCHAR(50) NOT NULL,
    country_code VARCHAR(10) NOT NULL,
    rating_system VARCHAR(50),
    source_name VARCHAR(50) NOT NULL,
    source_priority INTEGER,
    notes TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_content_certifications_content_country_system_source
        UNIQUE (content_id, country_code, rating_system, source_name)
);

CREATE TABLE IF NOT EXISTS content_videos (
    id BIGSERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL DEFAULT 'tmdb',
    source_video_id VARCHAR(255) NOT NULL,
    site VARCHAR(50) NOT NULL,
    video_type VARCHAR(50),
    name TEXT,
    official BOOLEAN,
    language_code VARCHAR(16),
    country_code VARCHAR(16),
    published_at TIMESTAMPTZ,
    size INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_content_videos_source_identity
        UNIQUE (content_id, source, site, source_video_id),
    CONSTRAINT uq_content_videos_content_id_id UNIQUE (content_id, id),
    CONSTRAINT chk_content_videos_size CHECK (size IS NULL OR size >= 0)
);

CREATE TABLE IF NOT EXISTS content_primary_videos (
    content_id INTEGER PRIMARY KEY REFERENCES content(id) ON DELETE CASCADE,
    content_video_id BIGINT NOT NULL UNIQUE,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_content_primary_videos_owned_video
        FOREIGN KEY (content_id, content_video_id)
        REFERENCES content_videos(content_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_video_fetch_state (
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL,
    last_attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_fetched_at TIMESTAMPTZ,
    last_fetch_status VARCHAR(20) NOT NULL CHECK (
        last_fetch_status IN ('success', 'empty', 'failed', 'incomplete')
    ),
    last_fetch_error TEXT,
    last_fetch_retryable BOOLEAN NOT NULL DEFAULT FALSE,
    last_failure_class VARCHAR(50),
    consecutive_failure_count INTEGER NOT NULL DEFAULT 0 CHECK (
        consecutive_failure_count >= 0
    ),
    source_snapshot_empty BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (content_id, source),
    CONSTRAINT chk_content_video_fetch_state_empty_status CHECK (
        (last_fetch_status = 'empty' AND source_snapshot_empty)
        OR (last_fetch_status <> 'empty' AND NOT source_snapshot_empty)
    ),
    CONSTRAINT chk_content_video_fetch_state_failure_details CHECK (
        (
            last_fetch_status IN ('success', 'empty')
            AND NOT last_fetch_retryable
            AND last_failure_class IS NULL
            AND consecutive_failure_count = 0
        )
        OR (
            last_fetch_status IN ('failed', 'incomplete')
            AND last_failure_class IS NOT NULL
            AND consecutive_failure_count >= 1
        )
    )
);

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
    released_seasons_count INTEGER,
    announced_seasons_count INTEGER,
    next_season_number INTEGER,
    next_season_air_date DATE,
    next_season_year INTEGER,
    has_announced_season BOOLEAN DEFAULT FALSE,
    season_summary_note TEXT,
    source_name TEXT DEFAULT 'tmdb',
    last_refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE ratings (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL,
    platform_id INTEGER NOT NULL,
    original_score NUMERIC(5,2) NOT NULL,
    original_scale NUMERIC(5,2) NOT NULL,
    normalized_score NUMERIC(5,2) NOT NULL,
    rating_count INTEGER,
    reviewer_group VARCHAR(20) CHECK (reviewer_group IN ('critic', 'audience', 'general')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE,
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE
);

CREATE TABLE content_summary (
    id SERIAL PRIMARY KEY,
    content_id INTEGER UNIQUE NOT NULL,
    unified_score NUMERIC(5,2),
    critic_score NUMERIC(5,2),
    audience_score NUMERIC(5,2),
    review_summary TEXT,
    pros TEXT,
    cons TEXT,
    verdict VARCHAR(50),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE
);

CREATE TABLE watched (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    content_id INTEGER NOT NULL,
    watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE,
    UNIQUE (user_id, content_id)
);

CREATE TABLE watch_later (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    content_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE,
    UNIQUE (user_id, content_id)
);
