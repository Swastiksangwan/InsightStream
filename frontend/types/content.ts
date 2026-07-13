export type Content = {
  id: number;
  title: string;
  original_title?: string | null;
  type: "movie" | "series";
  overview?: string | null;
  poster?: string | null;
  backdrop?: string | null;
  release_date?: string | null;
  year?: number | null;
  runtime?: number | null;
  language?: string | null;
  original_language?: string | null;
  original_language_name?: string | null;
  age_rating?: string | null;
  age_rating_region?: string | null;
  age_rating_source?: string | null;
  age_rating_system?: string | null;
  unified_score?: number | null;
  source_count?: number | null;
  scoring_source_count?: number | null;
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

export type HomeQuickFilter = {
  label: string;
  filter_key: string;
};

export type HomeHero = {
  title: string;
  subtitle: string;
  quick_filters: HomeQuickFilter[];
};

export type HomeContentCard = {
  id: number;
  title: string;
  content_type: Content["type"];
  year?: number | null;
  poster_url?: string | null;
  backdrop_url?: string | null;
  runtime?: number | null;
  age_rating?: string | null;
  release_date?: string | null;
  unified_score?: number | null;
  source_count?: number | null;
  scoring_source_count?: number | null;
  primary_platform?: string | null;
  platforms: string[];
  decision_reason: string;
  chips: string[];
};

export type HomeBucket = {
  bucket_id: string;
  label: string;
  subtitle: string;
  refresh_strategy?: string | null;
  refresh_cadence?: string | null;
  items: HomeContentCard[];
};

export type HomeSection = {
  section_id: string;
  title: string;
  subtitle: string;
  section_type: "poster_rail" | "bucketed_rail" | string;
  refresh_strategy: string;
  refresh_cadence: string;
  items?: HomeContentCard[] | null;
  buckets?: HomeBucket[] | null;
};

export type HomeResponse = {
  hero: HomeHero;
  sections: HomeSection[];
  generated_for?: string | null;
  refresh_note?: string | null;
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

export type RatingSourceItem = {
  source_name: string;
  display_name: string;
  source_category: "audience" | "critic" | "theatrical" | "internal" | string;
  raw_score?: number | null;
  raw_score_scale?: number | null;
  normalized_score?: number | null;
  vote_count?: number | null;
  rating_count_label?: string | null;
  rating_url?: string | null;
  fetched_at?: string | null;
  included_in_unified_score?: boolean;
};

export type RatingsResponse = {
  unified_score?: number | null;
  source_count: number;
  scoring_source_count?: number;
  sources: RatingSourceItem[];
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

export type InsightSummarySignal = {
  label: string;
  value: string;
};

export type InsightSummary = {
  headline?: string | null;
  summary?: string | null;
  best_for: string[];
  key_signals: InsightSummarySignal[];
  watch_note?: string | null;
  generated_from: string[];
  confidence: "low" | "medium" | "high" | string;
};

export type DecisionDisplayFact = {
  label: string;
  value: string;
};

export type DecisionDisplayProfile = {
  identity?: string[];
  themes?: string[];
  feel?: string[];
  pace?: string | null;
  best_for?: string[];
  consider_first?: string[];
};

export type DecisionDisplay = {
  primary_insight?: string | null;
  profile?: DecisionDisplayProfile | null;
  supporting_facts?: DecisionDisplayFact[];
};

export type DecisionLayer = {
  display?: DecisionDisplay | null;
  watch_profile?: unknown;
  decision_support?: unknown;
  signal_quality?: unknown;
};

export type ContentDetailsResponse = {
  content: Content;
  genres: string[];
  platforms: PlatformAvailability[];
  ratings: RatingsResponse;
  series_metadata?: SeriesMetadata | null;
  insight_summary: InsightSummary;
  decision_layer?: DecisionLayer | null;
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
