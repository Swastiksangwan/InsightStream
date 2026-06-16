export type PersonDetail = {
  person_id: number;
  name: string;
  profile_url?: string | null;
  known_for_department?: string | null;
  biography?: string | null;
};

export type PersonCreditItem = {
  content_id: number;
  title: string;
  content_type: "movie" | "series" | string;
  poster_url?: string | null;
  year?: number | null;
  character_name?: string | null;
  job?: string | null;
  department?: string | null;
  display_order?: number | null;
};

export type PersonCreditsResponse = {
  person_id: number;
  cast: PersonCreditItem[];
  directed: PersonCreditItem[];
  created: PersonCreditItem[];
  crew: PersonCreditItem[];
};
