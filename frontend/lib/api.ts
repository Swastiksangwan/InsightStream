import type {
  ContentDetailsResponse,
  DiscoverContentParams,
  Genre,
  PaginatedContentResponse,
  PlatformMetadata,
  PlatformType,
  UserContentActionRequest,
  UserContentActionResponse,
  UserContentItem,
} from "@/types/content";
import type { ContentCreditsResponse } from "@/types/credits";
import type { PersonCreditsResponse, PersonDetail } from "@/types/people";
import type { SearchResponse, SearchType } from "@/types/search";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL;
}

function buildUrl(
  path: string,
  params: Record<string, string | number | null | undefined> = {},
) {
  const url = new URL(path, getApiBaseUrl());

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });

  return url.toString();
}

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

async function parseErrorMessage(response: Response) {
  try {
    const payload = (await response.json()) as {
      detail?: string;
      message?: string;
    };

    return payload.detail || payload.message;
  } catch {
    return null;
  }
}

async function fetchFromApi<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const message = await parseErrorMessage(response);
    throw new ApiRequestError(
      message || `API request failed with status ${response.status}`,
      response.status,
    );
  }

  return response.json() as Promise<T>;
}

function normalizeLimit(limit: number) {
  return Math.min(Math.max(Math.trunc(limit), 1), 100);
}

export function getRecentContent(limit = 8) {
  return fetchFromApi<PaginatedContentResponse>(
    buildUrl("/content/recent", { limit: normalizeLimit(limit) }),
  );
}

export function getTopRatedContent(limit = 8) {
  return fetchFromApi<PaginatedContentResponse>(
    buildUrl("/content/top-rated", { limit: normalizeLimit(limit) }),
  );
}

export function getContentDetails(contentId: number | string) {
  return fetchFromApi<ContentDetailsResponse>(
    buildUrl(`/content/${contentId}/details`, {}),
  );
}

export function getContentCredits(contentId: number | string) {
  return fetchFromApi<ContentCreditsResponse>(
    buildUrl(`/content/${contentId}/credits`, {}),
  );
}

export function getPerson(personId: number | string) {
  return fetchFromApi<PersonDetail>(buildUrl(`/people/${personId}`, {}));
}

export function getPersonCredits(personId: number | string) {
  return fetchFromApi<PersonCreditsResponse>(
    buildUrl(`/people/${personId}/credits`, {}),
  );
}

export function searchCatalog(
  query: string,
  searchType: SearchType = "all",
  limit = 20,
  offset = 0,
) {
  return fetchFromApi<SearchResponse>(
    buildUrl("/search", {
      q: query,
      type: searchType,
      limit: normalizeLimit(limit),
      offset,
    }),
  );
}

export function getDiscoverContent(params: DiscoverContentParams = {}) {
  return fetchFromApi<PaginatedContentResponse>(
    buildUrl("/content/discover", {
      ...params,
      limit: params.limit ? normalizeLimit(params.limit) : undefined,
      offset: params.offset,
    }),
  );
}

export function getGenres() {
  return fetchFromApi<Genre[]>(buildUrl("/genres"));
}

export function getPlatforms(platformType?: PlatformType) {
  return fetchFromApi<PlatformMetadata[]>(
    buildUrl("/platforms", { platform_type: platformType }),
  );
}

function buildUserContentBody(
  userId: number,
  contentId: number,
): UserContentActionRequest {
  return {
    user_id: userId,
    content_id: contentId,
  };
}

export function addToWatchLater(userId: number, contentId: number) {
  return fetchFromApi<UserContentActionResponse>(buildUrl("/watch-later"), {
    method: "POST",
    body: JSON.stringify(buildUserContentBody(userId, contentId)),
  });
}

export function addToWatched(userId: number, contentId: number) {
  return fetchFromApi<UserContentActionResponse>(buildUrl("/watched"), {
    method: "POST",
    body: JSON.stringify(buildUserContentBody(userId, contentId)),
  });
}

export function removeFromWatchLater(userId: number, contentId: number) {
  return fetchFromApi<UserContentActionResponse>(buildUrl("/watch-later"), {
    method: "DELETE",
    body: JSON.stringify(buildUserContentBody(userId, contentId)),
  });
}

export function removeFromWatched(userId: number, contentId: number) {
  return fetchFromApi<UserContentActionResponse>(buildUrl("/watched"), {
    method: "DELETE",
    body: JSON.stringify(buildUserContentBody(userId, contentId)),
  });
}

export function getWatchLater(userId: number) {
  return fetchFromApi<UserContentItem[]>(buildUrl(`/watch-later/${userId}`));
}

export function getWatched(userId: number) {
  return fetchFromApi<UserContentItem[]>(buildUrl(`/watched/${userId}`));
}
