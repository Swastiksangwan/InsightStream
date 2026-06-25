-- ============================================================
-- InsightStream Database Indexes
-- Purpose:
-- Improve performance for content listing, discovery, search,
-- filtering, joins, and user watch-state APIs.
-- ============================================================


-- ------------------------------------------------------------
-- Content table indexes
-- ------------------------------------------------------------

-- Speeds up filtering by movie/series.
CREATE INDEX IF NOT EXISTS idx_content_content_type
ON content (content_type);

-- Speeds up recent content sorting.
CREATE INDEX IF NOT EXISTS idx_content_release_date
ON content (release_date DESC);

-- Speeds up recent sorting when series use a latest activity date.
CREATE INDEX IF NOT EXISTS idx_content_latest_activity_date
ON content (latest_activity_date DESC);

-- Speeds up common discovery sorting by type + release date.
CREATE INDEX IF NOT EXISTS idx_content_type_release_date
ON content (content_type, release_date DESC);

-- Speeds up common discovery sorting by type + latest activity date.
CREATE INDEX IF NOT EXISTS idx_content_type_latest_activity_date
ON content (content_type, latest_activity_date DESC);

-- Speeds up case-insensitive title search using ILIKE.
CREATE INDEX IF NOT EXISTS idx_content_title_lower
ON content (LOWER(title));

-- Speeds up local catalog search over content type labels.
CREATE INDEX IF NOT EXISTS idx_content_content_type_lower
ON content (LOWER(content_type));


-- ------------------------------------------------------------
-- People and credits indexes
-- ------------------------------------------------------------

-- Speeds up person name lookup and future person search.
CREATE INDEX IF NOT EXISTS idx_people_name
ON people (name);

-- Speeds up case-insensitive person search.
CREATE INDEX IF NOT EXISTS idx_people_name_lower
ON people (LOWER(name));

-- Speeds up filtering people by known department if needed later.
CREATE INDEX IF NOT EXISTS idx_people_known_for_department
ON people (known_for_department);

-- Speeds up case-insensitive department search.
CREATE INDEX IF NOT EXISTS idx_people_known_for_department_lower
ON people (LOWER(known_for_department));

-- Speeds up joining person external IDs back to people.
CREATE INDEX IF NOT EXISTS idx_person_external_ids_person_id
ON person_external_ids (person_id);

-- Speeds up fetching credits for a content detail page.
CREATE INDEX IF NOT EXISTS idx_content_people_content_id
ON content_people (content_id);

-- Speeds up fetching a person's credits later.
CREATE INDEX IF NOT EXISTS idx_content_people_person_id
ON content_people (person_id);

-- Speeds up role-based credit filtering.
CREATE INDEX IF NOT EXISTS idx_content_people_role_type
ON content_people (role_type);

-- Speeds up ordered cast/director/creator retrieval for one title.
CREATE INDEX IF NOT EXISTS idx_content_people_content_role_order
ON content_people (content_id, role_type, display_order);


-- ------------------------------------------------------------
-- Content summary indexes
-- ------------------------------------------------------------

-- Speeds up top-rated sorting.
CREATE INDEX IF NOT EXISTS idx_content_summary_unified_score
ON content_summary (unified_score DESC);

-- Speeds up joining content_summary with content.
CREATE INDEX IF NOT EXISTS idx_content_summary_content_id
ON content_summary (content_id);


-- ------------------------------------------------------------
-- Genre indexes
-- ------------------------------------------------------------

-- Speeds up case-insensitive genre lookup.
CREATE INDEX IF NOT EXISTS idx_genres_name_lower
ON genres (LOWER(name));

-- Speeds up joining content to genres.
CREATE INDEX IF NOT EXISTS idx_content_genres_content_id
ON content_genres (content_id);

CREATE INDEX IF NOT EXISTS idx_content_genres_genre_id
ON content_genres (genre_id);

-- Speeds up combined genre/content lookup.
CREATE INDEX IF NOT EXISTS idx_content_genres_content_genre
ON content_genres (content_id, genre_id);


-- ------------------------------------------------------------
-- Platform indexes
-- ------------------------------------------------------------

-- Speeds up case-insensitive platform lookup.
CREATE INDEX IF NOT EXISTS idx_platforms_name_lower
ON platforms (LOWER(name));

-- Speeds up filtering platforms by platform type.
CREATE INDEX IF NOT EXISTS idx_platforms_platform_type
ON platforms (platform_type);

-- Speeds up joining content to platforms.
CREATE INDEX IF NOT EXISTS idx_content_platforms_content_id
ON content_platforms (content_id);

CREATE INDEX IF NOT EXISTS idx_content_platforms_platform_id
ON content_platforms (platform_id);

-- Speeds up filtering by availability type.
CREATE INDEX IF NOT EXISTS idx_content_platforms_availability_type
ON content_platforms (availability_type);

-- Speeds up combined platform + availability discovery filters.
CREATE INDEX IF NOT EXISTS idx_content_platforms_platform_availability
ON content_platforms (platform_id, availability_type);

-- Speeds up region-aware provider availability lookup.
CREATE INDEX IF NOT EXISTS idx_content_availability_content_id
ON content_availability (content_id);

CREATE INDEX IF NOT EXISTS idx_content_availability_platform_id
ON content_availability (platform_id);

CREATE INDEX IF NOT EXISTS idx_content_availability_region_code
ON content_availability (region_code);

CREATE INDEX IF NOT EXISTS idx_content_availability_source_name
ON content_availability (source_name);

CREATE INDEX IF NOT EXISTS idx_content_availability_availability_type
ON content_availability (availability_type);

CREATE INDEX IF NOT EXISTS idx_content_availability_content_region
ON content_availability (content_id, region_code);

-- Speeds up region/source-aware certification lookup.
CREATE INDEX IF NOT EXISTS idx_content_certifications_content_id
ON content_certifications (content_id);

CREATE INDEX IF NOT EXISTS idx_content_certifications_country_code
ON content_certifications (country_code);

CREATE INDEX IF NOT EXISTS idx_content_certifications_source_name
ON content_certifications (source_name);


-- ------------------------------------------------------------
-- Series lifecycle metadata indexes
-- ------------------------------------------------------------

-- Speeds up filtering and reporting by normalized series lifecycle status.
CREATE INDEX IF NOT EXISTS idx_content_series_metadata_status_normalized
ON content_series_metadata (series_status_normalized);

-- Speeds up series recency and lifecycle reporting.
CREATE INDEX IF NOT EXISTS idx_content_series_metadata_last_air_date
ON content_series_metadata (last_air_date);

-- Speeds up upcoming/returning series lookup.
CREATE INDEX IF NOT EXISTS idx_content_series_metadata_next_episode_air_date
ON content_series_metadata (next_episode_air_date);

-- Speeds up season summary and upcoming season reporting.
CREATE INDEX IF NOT EXISTS idx_content_series_metadata_has_announced_season
ON content_series_metadata (has_announced_season);

CREATE INDEX IF NOT EXISTS idx_content_series_metadata_next_season_air_date
ON content_series_metadata (next_season_air_date);


-- ------------------------------------------------------------
-- Ratings indexes
-- ------------------------------------------------------------

-- Speeds up fetching provider-neutral ratings for content details.
CREATE INDEX IF NOT EXISTS idx_content_ratings_content_id
ON content_ratings (content_id);

-- Speeds up joining content ratings to rating sources.
CREATE INDEX IF NOT EXISTS idx_content_ratings_rating_source_id
ON content_ratings (rating_source_id);

-- Speeds up source-specific rating reporting and future sorting.
CREATE INDEX IF NOT EXISTS idx_content_ratings_source_normalized_score
ON content_ratings (rating_source_id, normalized_score);

-- Speeds up rating source lookup by provider-neutral source key.
CREATE INDEX IF NOT EXISTS idx_rating_sources_source_name
ON rating_sources (source_name);

-- Speeds up fetching ratings for content details.
CREATE INDEX IF NOT EXISTS idx_ratings_content_id
ON ratings (content_id);

-- Speeds up joining ratings with platforms.
CREATE INDEX IF NOT EXISTS idx_ratings_platform_id
ON ratings (platform_id);

-- Speeds up reviewer-group based ordering/filtering if needed later.
CREATE INDEX IF NOT EXISTS idx_ratings_reviewer_group
ON ratings (reviewer_group);


-- ------------------------------------------------------------
-- Watch later indexes
-- ------------------------------------------------------------

-- Speeds up fetching watch later list for a user.
CREATE INDEX IF NOT EXISTS idx_watch_later_user_id
ON watch_later (user_id);

-- Speeds up checking whether content is already in watch later.
CREATE INDEX IF NOT EXISTS idx_watch_later_user_content
ON watch_later (user_id, content_id);


-- ------------------------------------------------------------
-- Watched indexes
-- ------------------------------------------------------------

-- Speeds up fetching watched list for a user.
CREATE INDEX IF NOT EXISTS idx_watched_user_id
ON watched (user_id);

-- Speeds up checking whether content is already watched.
CREATE INDEX IF NOT EXISTS idx_watched_user_content
ON watched (user_id, content_id);
