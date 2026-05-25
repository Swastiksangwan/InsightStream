-- ============================================================
-- InsightStream Canonical Local Development Seed Data
-- Purpose:
-- Seed a reset-safe local dataset for the current backend APIs,
-- including content listing, details, discovery, metadata, ratings,
-- summaries, and user watch-state examples.
--
-- This file intentionally avoids hardcoded generated IDs.
-- Relationships are created through stable natural keys:
-- tmdb_id, genre name, platform name, and user email.
-- ============================================================

BEGIN;


-- ------------------------------------------------------------
-- Genres
-- ------------------------------------------------------------

INSERT INTO genres (name) VALUES
('Action'),
('Adventure'),
('Animation'),
('Comedy'),
('Crime'),
('Documentary'),
('Drama'),
('Fantasy'),
('Horror'),
('Mystery'),
('Romance'),
('Sci-Fi'),
('Thriller')
ON CONFLICT (name) DO NOTHING;


-- ------------------------------------------------------------
-- Platforms
-- ------------------------------------------------------------

INSERT INTO platforms (name, platform_type) VALUES
('Netflix', 'ott'),
('Prime Video', 'ott'),
('Disney+ Hotstar', 'ott'),
('JioCinema', 'ott'),
('Zee5', 'ott'),
('SonyLIV', 'ott'),
('Apple TV+', 'ott'),
('IMDb', 'rating_source'),
('Rotten Tomatoes', 'rating_source'),
('Metacritic', 'rating_source')
ON CONFLICT (name) DO UPDATE
SET platform_type = EXCLUDED.platform_type;


-- ------------------------------------------------------------
-- Content
-- ------------------------------------------------------------

INSERT INTO content (
    tmdb_id,
    title,
    content_type,
    overview,
    poster_url,
    backdrop_url,
    release_date,
    year,
    runtime,
    language,
    status,
    age_rating
) VALUES
(
    157336,
    'Interstellar',
    'movie',
    'A team of explorers travel through a wormhole in space in an attempt to ensure humanity''s survival.',
    'https://image.tmdb.org/t/p/w500/sampleposter.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop.jpg',
    '2014-11-07',
    2014,
    169,
    'English',
    'Released',
    'PG-13'
),
(
    157337,
    'Inception',
    'movie',
    'A thief who steals corporate secrets through dream-sharing technology is given a chance to erase his past crimes.',
    'https://image.tmdb.org/t/p/w500/sampleposter2.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop2.jpg',
    '2010-07-16',
    2010,
    148,
    'English',
    'Released',
    'PG-13'
),
(
    157338,
    'Breaking Bad',
    'series',
    'A high school chemistry teacher turns to manufacturing methamphetamine after a life-changing diagnosis.',
    'https://image.tmdb.org/t/p/w500/sampleposter3.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop3.jpg',
    '2008-01-20',
    2008,
    60,
    'English',
    'Released',
    'TV-MA'
),
(
    157339,
    'The Mandalorian',
    'series',
    'A lone bounty hunter travels through the outer reaches of the galaxy while protecting a mysterious child.',
    'https://image.tmdb.org/t/p/w500/sampleposter4.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop4.jpg',
    '2019-11-12',
    2019,
    50,
    'English',
    'Released',
    'TV-14'
)
ON CONFLICT (tmdb_id) DO UPDATE
SET
    title = EXCLUDED.title,
    content_type = EXCLUDED.content_type,
    overview = EXCLUDED.overview,
    poster_url = EXCLUDED.poster_url,
    backdrop_url = EXCLUDED.backdrop_url,
    release_date = EXCLUDED.release_date,
    year = EXCLUDED.year,
    runtime = EXCLUDED.runtime,
    language = EXCLUDED.language,
    status = EXCLUDED.status,
    age_rating = EXCLUDED.age_rating,
    updated_at = CURRENT_TIMESTAMP;


-- ------------------------------------------------------------
-- Content-Genre Relationships
-- ------------------------------------------------------------

DELETE FROM content_genres cg
USING content c
WHERE cg.content_id = c.id
  AND c.tmdb_id IN (157336, 157337, 157338, 157339);

INSERT INTO content_genres (content_id, genre_id)
SELECT
    c.id,
    g.id
FROM (
    VALUES
        (157336, 'Adventure'),
        (157336, 'Drama'),
        (157336, 'Sci-Fi'),
        (157337, 'Action'),
        (157337, 'Sci-Fi'),
        (157337, 'Thriller'),
        (157338, 'Crime'),
        (157338, 'Drama'),
        (157338, 'Thriller'),
        (157339, 'Action'),
        (157339, 'Adventure'),
        (157339, 'Sci-Fi')
) AS seed(tmdb_id, genre_name)
JOIN content c ON c.tmdb_id = seed.tmdb_id
JOIN genres g ON g.name = seed.genre_name
ON CONFLICT (content_id, genre_id) DO NOTHING;


-- ------------------------------------------------------------
-- Content Platform Availability
-- ------------------------------------------------------------

DELETE FROM content_platforms cp
USING content c
WHERE cp.content_id = c.id
  AND c.tmdb_id IN (157336, 157337, 157338, 157339);

INSERT INTO content_platforms (content_id, platform_id, availability_type)
SELECT
    c.id,
    p.id,
    seed.availability_type
FROM (
    VALUES
        (157336, 'Prime Video', 'streaming'),
        (157336, 'Apple TV+', 'rent'),
        (157337, 'Netflix', 'streaming'),
        (157337, 'Prime Video', 'rent'),
        (157338, 'Prime Video', 'streaming'),
        (157338, 'Netflix', 'streaming'),
        (157339, 'Disney+ Hotstar', 'streaming')
) AS seed(tmdb_id, platform_name, availability_type)
JOIN content c ON c.tmdb_id = seed.tmdb_id
JOIN platforms p ON p.name = seed.platform_name
ON CONFLICT (content_id, platform_id, availability_type) DO NOTHING;


-- ------------------------------------------------------------
-- Ratings
-- ratings has no unique constraint, so this file first removes
-- seeded-content ratings and then reinserts the canonical set.
-- ------------------------------------------------------------

DELETE FROM ratings r
USING content c
WHERE r.content_id = c.id
  AND c.tmdb_id IN (157336, 157337, 157338, 157339);

INSERT INTO ratings (
    content_id,
    platform_id,
    original_score,
    original_scale,
    normalized_score,
    rating_count,
    reviewer_group
)
SELECT
    c.id,
    p.id,
    seed.original_score,
    seed.original_scale,
    seed.normalized_score,
    seed.rating_count,
    seed.reviewer_group
FROM (
    VALUES
        (157336, 'IMDb', 8.70, 10.00, 87.00, 2000000, 'general'),
        (157336, 'Rotten Tomatoes', 73.00, 100.00, 73.00, 500, 'critic'),
        (157336, 'Metacritic', 74.00, 100.00, 74.00, 60, 'critic'),
        (157337, 'IMDb', 8.80, 10.00, 88.00, 2500000, 'general'),
        (157337, 'Rotten Tomatoes', 87.00, 100.00, 87.00, 400, 'critic'),
        (157337, 'Metacritic', 74.00, 100.00, 74.00, 45, 'critic'),
        (157338, 'IMDb', 9.50, 10.00, 95.00, 2200000, 'general'),
        (157338, 'Rotten Tomatoes', 96.00, 100.00, 96.00, 120, 'critic'),
        (157338, 'Metacritic', 87.00, 100.00, 87.00, 30, 'critic'),
        (157339, 'IMDb', 8.60, 10.00, 86.00, 600000, 'general'),
        (157339, 'Rotten Tomatoes', 90.00, 100.00, 90.00, 200, 'critic'),
        (157339, 'Metacritic', 70.00, 100.00, 70.00, 25, 'critic')
) AS seed(
    tmdb_id,
    platform_name,
    original_score,
    original_scale,
    normalized_score,
    rating_count,
    reviewer_group
)
JOIN content c ON c.tmdb_id = seed.tmdb_id
JOIN platforms p ON p.name = seed.platform_name;


-- ------------------------------------------------------------
-- Content Summaries
-- ------------------------------------------------------------

INSERT INTO content_summary (
    content_id,
    unified_score,
    critic_score,
    audience_score,
    review_summary,
    pros,
    cons,
    verdict
)
SELECT
    c.id,
    seed.unified_score,
    seed.critic_score,
    seed.audience_score,
    seed.review_summary,
    seed.pros,
    seed.cons,
    seed.verdict
FROM (
    VALUES
        (
            157336,
            78.00,
            73.50,
            87.00,
            'A visually ambitious and emotionally powerful science-fiction film that is widely appreciated for its scale, performances, and music.',
            'Strong visuals, emotional depth, memorable soundtrack',
            'Complex pacing and scientific heaviness may not appeal to all viewers',
            'Highly Recommended'
        ),
        (
            157337,
            85.00,
            80.50,
            88.00,
            'An intelligent and intricate thriller that combines high-concept storytelling with large-scale action.',
            'Inventive premise, strong action, memorable score',
            'Layered structure can be confusing on first watch',
            'Highly Recommended'
        ),
        (
            157338,
            92.00,
            91.50,
            95.00,
            'A landmark crime drama with exceptional writing, performances, and long-form character development.',
            'Outstanding performances, strong writing, tense progression',
            'Dark tone and slow-burn pacing may not suit every viewer',
            'Must Watch'
        ),
        (
            157339,
            87.00,
            80.00,
            86.00,
            'A polished space-western series with strong world-building and accessible adventure storytelling.',
            'Strong production design, engaging episodic adventures, broad appeal',
            'Some episodes feel lighter or more standalone than others',
            'Recommended'
        )
) AS seed(
    tmdb_id,
    unified_score,
    critic_score,
    audience_score,
    review_summary,
    pros,
    cons,
    verdict
)
JOIN content c ON c.tmdb_id = seed.tmdb_id
ON CONFLICT (content_id) DO UPDATE
SET
    unified_score = EXCLUDED.unified_score,
    critic_score = EXCLUDED.critic_score,
    audience_score = EXCLUDED.audience_score,
    review_summary = EXCLUDED.review_summary,
    pros = EXCLUDED.pros,
    cons = EXCLUDED.cons,
    verdict = EXCLUDED.verdict,
    updated_at = CURRENT_TIMESTAMP;


-- ------------------------------------------------------------
-- Users and Watch-State Examples
-- ------------------------------------------------------------

INSERT INTO users (name, email, password_hash)
VALUES ('Test User', 'test@example.com', 'samplehash')
ON CONFLICT (email) DO UPDATE
SET
    name = EXCLUDED.name,
    password_hash = EXCLUDED.password_hash;

-- Clear only the seeded user's watch-state rows for seeded content.
DELETE FROM watch_later wl
USING users u, content c
WHERE wl.user_id = u.id
  AND wl.content_id = c.id
  AND u.email = 'test@example.com'
  AND c.tmdb_id IN (157336, 157337, 157338, 157339);

DELETE FROM watched w
USING users u, content c
WHERE w.user_id = u.id
  AND w.content_id = c.id
  AND u.email = 'test@example.com'
  AND c.tmdb_id IN (157336, 157337, 157338, 157339);

-- Canonical sample state:
-- Interstellar is watched, while The Mandalorian is saved for later.
-- No title is present in both watched and watch_later for the same user.
INSERT INTO watched (user_id, content_id)
SELECT
    u.id,
    c.id
FROM users u
JOIN content c ON c.tmdb_id = 157336
WHERE u.email = 'test@example.com'
ON CONFLICT (user_id, content_id) DO NOTHING;

INSERT INTO watch_later (user_id, content_id)
SELECT
    u.id,
    c.id
FROM users u
JOIN content c ON c.tmdb_id = 157339
WHERE u.email = 'test@example.com'
ON CONFLICT (user_id, content_id) DO NOTHING;


COMMIT;
