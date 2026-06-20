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
