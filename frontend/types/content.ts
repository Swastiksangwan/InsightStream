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
