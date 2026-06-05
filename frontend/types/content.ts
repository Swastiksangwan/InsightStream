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
};

export type PaginatedContentResponse = {
  items: Content[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformAvailability = {
  name: string;
  availability_type: "streaming" | "rent" | "buy" | string;
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
