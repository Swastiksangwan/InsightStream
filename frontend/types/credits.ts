export type CreditCastMember = {
  person_id: number;
  name: string;
  character_name?: string | null;
  profile_url?: string | null;
  known_for_department?: string | null;
  display_order?: number | null;
};

export type CreditCrewMember = {
  person_id: number;
  name: string;
  profile_url?: string | null;
  known_for_department?: string | null;
  job?: string | null;
  department?: string | null;
  role_type?: "director" | "creator" | "crew" | string | null;
  display_order?: number | null;
};

export type ContentCreditsResponse = {
  content_id: number;
  cast: CreditCastMember[];
  directors: CreditCrewMember[];
  creators: CreditCrewMember[];
  crew: CreditCrewMember[];
};
