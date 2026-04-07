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
('Thriller');

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
('Metacritic', 'rating_source');

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
) VALUES (
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
);

INSERT INTO content_genres (content_id, genre_id) VALUES
(1, 2),
(1, 7),
(1, 12);

INSERT INTO content_platforms (content_id, platform_id, availability_type) VALUES
(1, 2, 'streaming');

INSERT INTO ratings (
    content_id,
    platform_id,
    original_score,
    original_scale,
    normalized_score,
    rating_count,
    reviewer_group
) VALUES
(1, 8, 8.70, 10.00, 87.00, 2000000, 'general'),
(1, 9, 73.00, 100.00, 73.00, 500, 'critic'),
(1, 10, 74.00, 100.00, 74.00, 60, 'critic');

INSERT INTO content_summary (
    content_id,
    unified_score,
    critic_score,
    audience_score,
    review_summary,
    pros,
    cons,
    verdict
) VALUES (
    1,
    78.00,
    73.50,
    87.00,
    'A visually ambitious and emotionally powerful science-fiction film that is widely appreciated for its scale, performances, and music.',
    'Strong visuals, emotional depth, memorable soundtrack',
    'Complex pacing and scientific heaviness may not appeal to all viewers',
    'Highly Recommended'
);

INSERT INTO users (name, email, password_hash)
VALUES ('Test User', 'test@example.com', 'samplehash');

INSERT INTO watch_later (user_id, content_id)
VALUES (1, 1);

INSERT INTO watched (user_id, content_id)

VALUES (1, 1);
