import type {
  ContentDetailsResponse,
  PaginatedContentResponse,
} from "@/types/content";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL;
}

function buildUrl(path: string, params: Record<string, string | number>) {
  const url = new URL(path, getApiBaseUrl());

  Object.entries(params).forEach(([key, value]) => {
    url.searchParams.set(key, String(value));
  });

  return url.toString();
}

async function fetchFromApi<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
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
