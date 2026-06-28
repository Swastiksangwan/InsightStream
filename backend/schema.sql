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
    content_type VARCHAR(20) NOT NULL CHECK (content_type IN ('movie', 'series')),
    overview TEXT,
    poster_url TEXT,
    backdrop_url TEXT,
    release_date DATE,
    latest_activity_date DATE,
    year INTEGER,
    runtime INTEGER,
    language VARCHAR(50),
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
