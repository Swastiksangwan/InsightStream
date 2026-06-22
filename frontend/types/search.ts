export type SearchType = "all" | "content" | "person";

export type ContentSearchResult = {
  id: number;
  title: string;
  content_type: "movie" | "series" | string;
  overview_snippet?: string | null;
  poster_url?: string | null;
  backdrop_url?: string | null;
  release_date?: string | null;
  latest_activity_date?: string | null;
  age_rating?: string | null;
  genres: string[];
  matched_people?: string[];
  match_reason?: string | null;
  result_type: "content";
};

export type PersonSearchResult = {
  id: number;
  name: string;
  profile_url?: string | null;
  known_for_department?: string | null;
  biography_snippet?: string | null;
  match_reason?: string | null;
  result_type: "person";
};

export type SearchResponse = {
  query: string;
  type: SearchType;
  content_results: ContentSearchResult[];
  person_results: PersonSearchResult[];
  total_content_results: number;
  total_person_results: number;
};
