-- Insert sample genres
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

-- Insert sample platforms
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

-- Insert sample content
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

-- Insert more sample content with different genres
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
(157337, 'Inception', 'movie', 'A thief who steals corporate secrets through the use of dream-sharing technology.', 'https://image.tmdb.org/t/p/w500/sampleposter2.jpg', 'https://image.tmdb.org/t/p/original/samplebackdrop2.jpg', '2010-07-16', 2010, 148, 'English', 'Released', 'PG-13'),
(157338, 'Breaking Bad', 'series', 'A high school chemistry teacher turned methamphetamine manufacturer.', 'https://image.tmdb.org/t/p/w500/sampleposter3.jpg', 'https://image.tmdb.org/t/p/original/samplebackdrop3.jpg', '2008-01-20', 2008, 60, 'English', 'Released', 'TV-MA'),
(157339, 'The Mandalorian', 'series', 'The travels of a lone bounty hunter in the outer reaches of the galaxy.', 'https://image.tmdb.org/t/p/w500/sampleposter4.jpg', 'https://image.tmdb.org/t/p/original/samplebackdrop4.jpg', '2019-11-12', 2019, 50, 'English', 'Released', 'PG-13');

INSERT INTO content_genres (content_id, genre_id) VALUES
(9, 41),  -- Interstellar -> Adventure
(9, 46),  -- Interstellar -> Drama
(9, 51), -- Interstellar -> Sci-Fi
(10, 40), -- Inception -> Action
(10, 51); -- Inception -> Sci-Fi

select * from watch_later;

-- Link content to platforms
INSERT INTO content_platforms (content_id, platform_id, availability_type) VALUES
(9, 22, 'streaming'),  -- Interstellar -> Prime Video
(10, 21, 'streaming'),  -- Inception -> Netflix
(11, 22, 'streaming'),  -- Breaking Bad -> Prime Video
(12, 23, 'streaming');  -- The Mandalorian -> Disney+ Hotstar

-- Add sample ratings
INSERT INTO ratings (content_id, platform_id, original_score, original_scale, normalized_score, rating_count, reviewer_group)
VALUES
(9, 22, 8.70, 10.00, 87.00, 2000000, 'general'),  -- Interstellar -> IMDb
(10, 21, 7.50, 10.00, 75.00, 500000, 'critic'),  -- Inception -> Rotten Tomatoes
(11, 22, 8.80, 10.00, 88.00, 100000, 'critic'),  -- Breaking Bad -> Metacritic
(12, 23, 9.00, 10.00, 90.00, 1500000, 'general');  -- The Mandalorian -> IMDb

-- Insert content summaries
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
    9,
    78.00,
    73.50,
    87.00,
    'A visually ambitious and emotionally powerful science-fiction film that is widely appreciated for its scale, performances, and music.',
    'Strong visuals, emotional depth, memorable soundtrack',
    'Complex pacing and scientific heaviness may not appeal to all viewers',
    'Highly Recommended'
),
(
    10,
    85.00,
    80.00,
    90.00,
    'An intelligent and intricate film that challenges the mind while keeping the audience on the edge of their seat.',
    'Great plot, stunning visuals',
    'Can be confusing at times, slow pacing in certain scenes',
    'A must-watch for thriller fans'
),
(
    11,
    92.00,
    90.00,
    94.00,
    'A landmark TV series known for its complex characters and thrilling storylines.',
    'Outstanding performances, brilliant writing',
    'Some slow episodes in the middle',
    'The best TV show ever made'
),
(
    12,
    87.00,
    85.00,
    90.00,
    'A thrilling space-western set in the Star Wars universe with captivating characters.',
    'Great world-building, amazing visuals',
    'Some episodes feel slow or filler-heavy',
    'A great addition to the Star Wars franchise'
);


-- User adds content to 'watch_later' and 'watched' simultaneously
-- Remove from 'watch_later' when adding to 'watched'
DELETE FROM watch_later WHERE user_id = 1 AND content_id = 9;
INSERT INTO watch_later (user_id, content_id) VALUES (1, 9); -- Adding to watch_later
DELETE FROM watch_later WHERE user_id = 1 AND content_id = 9; -- Already added, so move to watched
INSERT INTO watched (user_id, content_id) VALUES (1, 9); -- Move to watched
