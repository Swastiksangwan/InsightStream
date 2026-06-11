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
--
-- Ratings and platform availability are plausible development data
-- for local testing, not authoritative production data.
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
-- Some poster/backdrop URLs below are TMDb-derived media values used
-- for local prototype development. TMDb requires attribution/licensing
-- consideration and remains a replaceable metadata provider.

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
    'https://image.tmdb.org/t/p/w500/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg',
    'https://image.tmdb.org/t/p/w1280/2ssWTSVklAEc98frZUQhgtGHx7s.jpg',
    '2014-11-07',
    2014,
    169,
    'English',
    'Released',
    'PG-13'
),
(
    27205,
    'Inception',
    'movie',
    'A thief who steals corporate secrets through dream-sharing technology is given a chance to erase his past crimes.',
    'https://image.tmdb.org/t/p/w500/xlaY2zyzMfkhk0HSC5VUwzoZPU1.jpg',
    'https://image.tmdb.org/t/p/w1280/8ZTVqvKDQ8emSGUEMjsS4yHAwrp.jpg',
    '2010-07-16',
    2010,
    148,
    'English',
    'Released',
    'PG-13'
),
(
    1396,
    'Breaking Bad',
    'series',
    'A high school chemistry teacher turns to manufacturing methamphetamine after a life-changing diagnosis.',
    'https://image.tmdb.org/t/p/w500/ztkUQFLlC19CCMYHW9o1zWhJRNq.jpg',
    'https://image.tmdb.org/t/p/w1280/tsRy63Mu5cu8etL1X7ZLyf7UP1M.jpg',
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
),
(
    155,
    'The Dark Knight',
    'movie',
    'Batman faces the Joker, a criminal mastermind who pushes Gotham City and its hero into chaos.',
    'https://image.tmdb.org/t/p/w500/qJ2tW6WMUDux911r6m7haRef0WH.jpg',
    'https://image.tmdb.org/t/p/w1280/cfT29Im5VDvjE0RpyKOSdCKZal7.jpg',
    '2008-07-18',
    2008,
    152,
    'English',
    'Released',
    'PG-13'
),
(
    496243,
    'Parasite',
    'movie',
    'A struggling family schemes its way into the lives of a wealthy household with unexpected consequences.',
    'https://image.tmdb.org/t/p/w500/sampleposter6.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop6.jpg',
    '2019-05-30',
    2019,
    132,
    'Korean',
    'Released',
    'R'
),
(
    693134,
    'Dune: Part Two',
    'movie',
    'Paul Atreides unites with the Fremen while seeking revenge and confronting a future shaped by prophecy.',
    'https://image.tmdb.org/t/p/w500/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg',
    'https://image.tmdb.org/t/p/w1280/xOMo8BRK7PfcJv9JCnx7s5hj0PX.jpg',
    '2024-03-01',
    2024,
    166,
    'English',
    'Released',
    'PG-13'
),
(
    346698,
    'Barbie',
    'movie',
    'Barbie leaves her perfect world and enters the real one, discovering identity, expectations, and change.',
    'https://image.tmdb.org/t/p/w500/sampleposter8.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop8.jpg',
    '2023-07-21',
    2023,
    114,
    'English',
    'Released',
    'PG-13'
),
(
    569094,
    'Spider-Man: Across the Spider-Verse',
    'movie',
    'Miles Morales travels across the multiverse and meets a team of Spider-People facing a difficult choice.',
    'https://image.tmdb.org/t/p/w500/sampleposter9.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop9.jpg',
    '2023-06-02',
    2023,
    140,
    'English',
    'Released',
    'PG'
),
(
    512195,
    'Red Notice',
    'movie',
    'An FBI profiler, an art thief, and a rival criminal cross paths during a globe-trotting heist chase.',
    'https://image.tmdb.org/t/p/w500/sampleposter10.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop10.jpg',
    '2021-11-12',
    2021,
    118,
    'English',
    'Released',
    'PG-13'
),
(
    100088,
    'The Last of Us',
    'series',
    'A smuggler escorts a teenager across a dangerous post-pandemic world after society has collapsed.',
    'https://image.tmdb.org/t/p/w500/sampleposter11.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop11.jpg',
    '2023-01-15',
    2023,
    55,
    'English',
    'Released',
    'TV-MA'
),
(
    66732,
    'Stranger Things',
    'series',
    'A group of kids in a small town face secret experiments, supernatural threats, and a mysterious alternate dimension.',
    'https://image.tmdb.org/t/p/w500/sampleposter12.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop12.jpg',
    '2016-07-15',
    2016,
    50,
    'English',
    'Released',
    'TV-14'
),
(
    76479,
    'The Boys',
    'series',
    'A group of vigilantes challenges corrupt superheroes and the corporation that protects their public image.',
    'https://image.tmdb.org/t/p/w500/sampleposter13.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop13.jpg',
    '2019-07-26',
    2019,
    60,
    'English',
    'Released',
    'TV-MA'
),
(
    70523,
    'Dark',
    'series',
    'A missing child leads four families into a mystery involving secrets, time, and a small town''s troubled past.',
    'https://image.tmdb.org/t/p/w500/sampleposter14.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop14.jpg',
    '2017-12-01',
    2017,
    53,
    'German',
    'Released',
    'TV-MA'
),
(
    71912,
    'The Witcher',
    'series',
    'A monster hunter struggles to find his place in a world where people often prove more dangerous than beasts.',
    'https://image.tmdb.org/t/p/w500/sampleposter15.jpg',
    'https://image.tmdb.org/t/p/original/samplebackdrop15.jpg',
    '2019-12-20',
    2019,
    60,
    'English',
    'Released',
    'TV-MA'
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
  AND c.tmdb_id IN (
      157336, 27205, 1396, 157339, 155,
      496243, 693134, 346698, 569094, 512195,
      100088, 66732, 76479, 70523, 71912
  );

INSERT INTO content_genres (content_id, genre_id)
SELECT
    c.id,
    g.id
FROM (
    VALUES
        (157336, 'Adventure'),
        (157336, 'Drama'),
        (157336, 'Sci-Fi'),
        (27205, 'Action'),
        (27205, 'Sci-Fi'),
        (27205, 'Thriller'),
        (1396, 'Crime'),
        (1396, 'Drama'),
        (1396, 'Thriller'),
        (157339, 'Action'),
        (157339, 'Adventure'),
        (157339, 'Sci-Fi'),
        (155, 'Action'),
        (155, 'Crime'),
        (155, 'Drama'),
        (155, 'Thriller'),
        (496243, 'Comedy'),
        (496243, 'Drama'),
        (496243, 'Thriller'),
        (693134, 'Adventure'),
        (693134, 'Drama'),
        (693134, 'Sci-Fi'),
        (346698, 'Adventure'),
        (346698, 'Comedy'),
        (346698, 'Fantasy'),
        (569094, 'Action'),
        (569094, 'Adventure'),
        (569094, 'Animation'),
        (569094, 'Sci-Fi'),
        (512195, 'Action'),
        (512195, 'Comedy'),
        (512195, 'Crime'),
        (100088, 'Drama'),
        (100088, 'Horror'),
        (100088, 'Thriller'),
        (66732, 'Drama'),
        (66732, 'Fantasy'),
        (66732, 'Horror'),
        (66732, 'Sci-Fi'),
        (76479, 'Action'),
        (76479, 'Comedy'),
        (76479, 'Crime'),
        (76479, 'Drama'),
        (70523, 'Crime'),
        (70523, 'Drama'),
        (70523, 'Mystery'),
        (70523, 'Sci-Fi'),
        (70523, 'Thriller'),
        (71912, 'Action'),
        (71912, 'Adventure'),
        (71912, 'Drama'),
        (71912, 'Fantasy')
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
  AND c.tmdb_id IN (
      157336, 27205, 1396, 157339, 155,
      496243, 693134, 346698, 569094, 512195,
      100088, 66732, 76479, 70523, 71912
  );

INSERT INTO content_platforms (content_id, platform_id, availability_type)
SELECT
    c.id,
    p.id,
    seed.availability_type
FROM (
    VALUES
        (157336, 'Prime Video', 'streaming'),
        (157336, 'Apple TV+', 'rent'),
        (27205, 'Netflix', 'streaming'),
        (27205, 'Prime Video', 'rent'),
        (1396, 'Prime Video', 'streaming'),
        (1396, 'Netflix', 'streaming'),
        (157339, 'Disney+ Hotstar', 'streaming'),
        (155, 'Prime Video', 'rent'),
        (155, 'Apple TV+', 'buy'),
        (496243, 'Prime Video', 'rent'),
        (496243, 'Apple TV+', 'buy'),
        (693134, 'Apple TV+', 'rent'),
        (693134, 'Prime Video', 'buy'),
        (346698, 'Prime Video', 'rent'),
        (346698, 'Apple TV+', 'buy'),
        (569094, 'Netflix', 'streaming'),
        (569094, 'Prime Video', 'rent'),
        (512195, 'Netflix', 'streaming'),
        (100088, 'JioCinema', 'streaming'),
        (100088, 'Apple TV+', 'buy'),
        (66732, 'Netflix', 'streaming'),
        (76479, 'Prime Video', 'streaming'),
        (70523, 'Netflix', 'streaming'),
        (71912, 'Netflix', 'streaming')
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
  AND c.tmdb_id IN (
      157336, 27205, 1396, 157339, 155,
      496243, 693134, 346698, 569094, 512195,
      100088, 66732, 76479, 70523, 71912
  );

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
        (157336, 'Rotten Tomatoes', 87.00, 100.00, 87.00, 250000, 'audience'),
        (157336, 'Metacritic', 74.00, 100.00, 74.00, 60, 'critic'),
        (27205, 'IMDb', 8.80, 10.00, 88.00, 2500000, 'general'),
        (27205, 'Rotten Tomatoes', 87.00, 100.00, 87.00, 400, 'critic'),
        (27205, 'Rotten Tomatoes', 91.00, 100.00, 91.00, 300000, 'audience'),
        (27205, 'Metacritic', 74.00, 100.00, 74.00, 45, 'critic'),
        (1396, 'IMDb', 9.50, 10.00, 95.00, 2200000, 'general'),
        (1396, 'Rotten Tomatoes', 96.00, 100.00, 96.00, 120, 'critic'),
        (1396, 'Rotten Tomatoes', 97.00, 100.00, 97.00, 500000, 'audience'),
        (1396, 'Metacritic', 87.00, 100.00, 87.00, 30, 'critic'),
        (157339, 'IMDb', 8.60, 10.00, 86.00, 600000, 'general'),
        (157339, 'Rotten Tomatoes', 90.00, 100.00, 90.00, 200, 'critic'),
        (157339, 'Rotten Tomatoes', 92.00, 100.00, 92.00, 180000, 'audience'),
        (157339, 'Metacritic', 70.00, 100.00, 70.00, 25, 'critic'),
        (155, 'IMDb', 9.00, 10.00, 90.00, 2800000, 'general'),
        (155, 'Rotten Tomatoes', 94.00, 100.00, 94.00, 350, 'critic'),
        (155, 'Rotten Tomatoes', 94.00, 100.00, 94.00, 700000, 'audience'),
        (155, 'Metacritic', 84.00, 100.00, 84.00, 45, 'critic'),
        (496243, 'IMDb', 8.50, 10.00, 85.00, 950000, 'general'),
        (496243, 'Rotten Tomatoes', 99.00, 100.00, 99.00, 480, 'critic'),
        (496243, 'Rotten Tomatoes', 90.00, 100.00, 90.00, 160000, 'audience'),
        (496243, 'Metacritic', 96.00, 100.00, 96.00, 55, 'critic'),
        (693134, 'IMDb', 8.50, 10.00, 85.00, 650000, 'general'),
        (693134, 'Rotten Tomatoes', 92.00, 100.00, 92.00, 430, 'critic'),
        (693134, 'Rotten Tomatoes', 95.00, 100.00, 95.00, 200000, 'audience'),
        (693134, 'Metacritic', 79.00, 100.00, 79.00, 60, 'critic'),
        (346698, 'IMDb', 6.80, 10.00, 68.00, 550000, 'general'),
        (346698, 'Rotten Tomatoes', 88.00, 100.00, 88.00, 480, 'critic'),
        (346698, 'Rotten Tomatoes', 83.00, 100.00, 83.00, 180000, 'audience'),
        (346698, 'Metacritic', 80.00, 100.00, 80.00, 65, 'critic'),
        (569094, 'IMDb', 8.60, 10.00, 86.00, 420000, 'general'),
        (569094, 'Rotten Tomatoes', 95.00, 100.00, 95.00, 380, 'critic'),
        (569094, 'Rotten Tomatoes', 94.00, 100.00, 94.00, 150000, 'audience'),
        (569094, 'Metacritic', 86.00, 100.00, 86.00, 55, 'critic'),
        (512195, 'IMDb', 6.30, 10.00, 63.00, 320000, 'general'),
        (512195, 'Rotten Tomatoes', 40.00, 100.00, 40.00, 180, 'critic'),
        (512195, 'Rotten Tomatoes', 75.00, 100.00, 75.00, 110000, 'audience'),
        (512195, 'Metacritic', 45.00, 100.00, 45.00, 35, 'critic'),
        (100088, 'IMDb', 8.70, 10.00, 87.00, 600000, 'general'),
        (100088, 'Rotten Tomatoes', 96.00, 100.00, 96.00, 300, 'critic'),
        (100088, 'Rotten Tomatoes', 89.00, 100.00, 89.00, 220000, 'audience'),
        (100088, 'Metacritic', 84.00, 100.00, 84.00, 45, 'critic'),
        (66732, 'IMDb', 8.70, 10.00, 87.00, 1400000, 'general'),
        (66732, 'Rotten Tomatoes', 92.00, 100.00, 92.00, 330, 'critic'),
        (66732, 'Rotten Tomatoes', 90.00, 100.00, 90.00, 400000, 'audience'),
        (66732, 'Metacritic', 74.00, 100.00, 74.00, 35, 'critic'),
        (76479, 'IMDb', 8.70, 10.00, 87.00, 650000, 'general'),
        (76479, 'Rotten Tomatoes', 93.00, 100.00, 93.00, 260, 'critic'),
        (76479, 'Rotten Tomatoes', 84.00, 100.00, 84.00, 210000, 'audience'),
        (76479, 'Metacritic', 77.00, 100.00, 77.00, 40, 'critic'),
        (70523, 'IMDb', 8.70, 10.00, 87.00, 450000, 'general'),
        (70523, 'Rotten Tomatoes', 95.00, 100.00, 95.00, 120, 'critic'),
        (70523, 'Rotten Tomatoes', 94.00, 100.00, 94.00, 160000, 'audience'),
        (70523, 'Metacritic', 82.00, 100.00, 82.00, 30, 'critic'),
        (71912, 'IMDb', 8.00, 10.00, 80.00, 600000, 'general'),
        (71912, 'Rotten Tomatoes', 67.00, 100.00, 67.00, 220, 'critic'),
        (71912, 'Rotten Tomatoes', 75.00, 100.00, 75.00, 190000, 'audience'),
        (71912, 'Metacritic', 53.00, 100.00, 53.00, 35, 'critic')
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
            27205,
            85.00,
            80.50,
            88.00,
            'An intelligent and intricate thriller that combines high-concept storytelling with large-scale action.',
            'Inventive premise, strong action, memorable score',
            'Layered structure can be confusing on first watch',
            'Highly Recommended'
        ),
        (
            1396,
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
        ),
        (
            155,
            91.00,
            89.00,
            94.00,
            'A tense superhero crime drama with memorable performances and strong mainstream appeal.',
            'Iconic villain, gripping pacing, strong action set pieces',
            'Dark tone and long runtime may not suit every casual viewer',
            'Highly Recommended'
        ),
        (
            496243,
            92.00,
            97.50,
            90.00,
            'A sharp social thriller with strong direction, layered themes, and broad critical praise.',
            'Original premise, excellent pacing, strong social commentary',
            'Tone shifts may feel uncomfortable for lighter viewing',
            'Highly Recommended'
        ),
        (
            693134,
            88.00,
            85.50,
            94.00,
            'A large-scale science-fiction sequel with strong spectacle, world-building, and dramatic momentum.',
            'Epic visuals, strong sound design, richer character stakes',
            'Dense lore and slower dramatic sections may not appeal to everyone',
            'Highly Recommended'
        ),
        (
            346698,
            82.00,
            84.00,
            83.00,
            'A colorful pop-culture comedy that mixes playful style with accessible social commentary.',
            'Distinct visual style, strong comedic energy, broad audience appeal',
            'Meta humor and tonal shifts may divide some viewers',
            'Recommended'
        ),
        (
            569094,
            91.00,
            90.50,
            94.00,
            'A visually inventive animated superhero film with fast pacing and strong emotional stakes.',
            'Innovative animation, energetic storytelling, strong character work',
            'Busy multiverse structure may feel overwhelming',
            'Highly Recommended'
        ),
        (
            512195,
            55.00,
            42.50,
            75.00,
            'A glossy action-comedy built for casual viewing, with broad appeal but mixed critical response.',
            'Fast pace, familiar stars, easy watchability',
            'Formulaic story and uneven humor limit replay value',
            'Casual Watch'
        ),
        (
            100088,
            90.00,
            90.00,
            89.00,
            'A tense post-apocalyptic drama with strong performances and emotionally grounded stakes.',
            'Strong performances, atmosphere, emotional character focus',
            'Bleak tone and slower episodes may not suit all viewers',
            'Highly Recommended'
        ),
        (
            66732,
            88.00,
            83.00,
            90.00,
            'A popular supernatural adventure series with strong nostalgia, mystery, and ensemble appeal.',
            'Memorable characters, accessible mystery, strong genre blend',
            'Later-season scale can feel uneven compared with early episodes',
            'Recommended'
        ),
        (
            76479,
            86.00,
            85.00,
            84.00,
            'A sharp and violent superhero satire with strong character conflicts and dark humor.',
            'Bold tone, strong satire, memorable ensemble',
            'Graphic violence and cynicism may not appeal to all viewers',
            'Recommended'
        ),
        (
            70523,
            89.00,
            88.50,
            94.00,
            'A complex mystery series with strong atmosphere, layered timelines, and dedicated fan appeal.',
            'Intricate plotting, strong atmosphere, rewarding long-form mystery',
            'Complex structure requires close attention',
            'Highly Recommended'
        ),
        (
            71912,
            70.00,
            60.00,
            75.00,
            'A fantasy adventure series with strong world appeal and mixed execution across seasons.',
            'Fantasy setting, action moments, strong fan interest',
            'Uneven pacing and mixed season quality affect consistency',
            'Good for Fans'
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
  AND c.tmdb_id IN (
      157336, 27205, 1396, 157339, 155,
      496243, 693134, 346698, 569094, 512195,
      100088, 66732, 76479, 70523, 71912
  );

DELETE FROM watched w
USING users u, content c
WHERE w.user_id = u.id
  AND w.content_id = c.id
  AND u.email = 'test@example.com'
  AND c.tmdb_id IN (
      157336, 27205, 1396, 157339, 155,
      496243, 693134, 346698, 569094, 512195,
      100088, 66732, 76479, 70523, 71912
  );

-- Canonical sample state:
-- Watched: Interstellar, Inception
-- Watch later: The Mandalorian, Dune: Part Two
-- No title is present in both watched and watch_later for the same user.
INSERT INTO watched (user_id, content_id)
SELECT
    u.id,
    c.id
FROM users u
JOIN content c ON c.tmdb_id IN (157336, 27205)
WHERE u.email = 'test@example.com'
ON CONFLICT (user_id, content_id) DO NOTHING;

INSERT INTO watch_later (user_id, content_id)
SELECT
    u.id,
    c.id
FROM users u
JOIN content c ON c.tmdb_id IN (157339, 693134)
WHERE u.email = 'test@example.com'
ON CONFLICT (user_id, content_id) DO NOTHING;


COMMIT;


-- ------------------------------------------------------------
-- Optional Verification Queries
-- Copy into pgAdmin after running this file if you want to
-- inspect the seeded local development data.
-- ------------------------------------------------------------

-- Total content count:
-- SELECT COUNT(*) AS total_content FROM content;

-- Content count by type:
-- SELECT content_type, COUNT(*) AS total
-- FROM content
-- GROUP BY content_type
-- ORDER BY content_type;

-- Genre relationships:
-- SELECT c.title, g.name AS genre
-- FROM content c
-- JOIN content_genres cg ON cg.content_id = c.id
-- JOIN genres g ON g.id = cg.genre_id
-- ORDER BY c.title, g.name;

-- Platform relationships:
-- SELECT c.title, p.name AS platform, cp.availability_type
-- FROM content c
-- JOIN content_platforms cp ON cp.content_id = c.id
-- JOIN platforms p ON p.id = cp.platform_id
-- ORDER BY c.title, p.name, cp.availability_type;

-- Ratings rows:
-- SELECT c.title, p.name AS source, r.reviewer_group, r.normalized_score
-- FROM ratings r
-- JOIN content c ON c.id = r.content_id
-- JOIN platforms p ON p.id = r.platform_id
-- ORDER BY c.title, r.reviewer_group, p.name;

-- Watch-state conflict check:
-- SELECT wl.user_id, wl.content_id, c.title
-- FROM watch_later wl
-- JOIN watched w
--     ON w.user_id = wl.user_id
--    AND w.content_id = wl.content_id
-- JOIN content c
--     ON c.id = wl.content_id
-- ORDER BY wl.user_id, wl.content_id;
