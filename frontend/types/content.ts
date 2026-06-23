export type Content = {
  id: number;
  title: string;
  type: "movie" | "series";
  overview?: string | null;
  poster?: string | null;
  backdrop?: string | null;
  release_date?: string | null;
  year?: number | null;
  runtime?: number | null;
  language?: string | null;
  age_rating?: string | null;
  age_rating_region?: string | null;
  age_rating_source?: string | null;
  age_rating_system?: string | null;
};

export type SeriesMetadata = {
  number_of_seasons?: number | null;
  number_of_episodes?: number | null;
  series_status?: string | null;
  series_status_normalized?: string | null;
  in_production?: boolean | null;
  first_air_date?: string | null;
  last_air_date?: string | null;
  last_episode_air_date?: string | null;
  next_episode_air_date?: string | null;
  series_type?: string | null;
  released_seasons_count?: number | null;
  announced_seasons_count?: number | null;
  next_season_number?: number | null;
  next_season_air_date?: string | null;
  next_season_year?: number | null;
  has_announced_season?: boolean | null;
  season_summary_note?: string | null;
};

export type PaginatedContentResponse = {
  items: Content[];
  total: number;
  limit: number;
  offset: number;
};

export type Genre = {
  id: number;
  name: string;
};

export type PlatformType = "ott" | "rating_source" | "review_source";

export type PlatformMetadata = {
  id: number;
  name: string;
  platform_type: PlatformType | string;
};

export type DiscoverContentParams = {
  content_type?: Content["type"];
  genre?: string;
  platform?: string;
  availability_type?: "streaming" | "rent" | "buy";
  sort_by?: "recent" | "top_rated";
  limit?: number;
  offset?: number;
};

export type PlatformAvailability = {
  name: string;
  availability_type: "streaming" | "rent" | "buy" | string;
  platform_type?: PlatformType | string | null;
  region_code?: string | null;
  source_name?: string | null;
  source_provider_id?: string | null;
  display_priority?: number | null;
};

export type Rating = {
  platform: string;
  original_score: number;
  original_scale: number;
  normalized_score: number;
  rating_count?: number | null;
  reviewer_group?: "critic" | "audience" | "general" | string | null;
};

export type Summary = {
  unified_score?: number | null;
  critic_score?: number | null;
  audience_score?: number | null;
  review_summary?: string | null;
  pros?: string | null;
  cons?: string | null;
  verdict?: string | null;
};

export type ContentDetailsResponse = {
  content: Content;
  genres: string[];
  platforms: PlatformAvailability[];
  ratings: Rating[];
  series_metadata?: SeriesMetadata | null;
  summary?: Summary | null;
};

export type UserContentActionRequest = {
  user_id: number;
  content_id: number;
};

export type UserContentActionResponse = {
  message: string;
};

export type UserContentItem = Content;

export type WatchStatus = "none" | "watch_later" | "watched";
