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
