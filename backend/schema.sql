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
    year INTEGER,
    runtime INTEGER,
    language VARCHAR(50),
    status VARCHAR(50),
    age_rating VARCHAR(20),
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

