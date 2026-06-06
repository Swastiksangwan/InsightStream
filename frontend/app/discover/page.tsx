import Link from "next/link";
import { ContentGrid } from "@/components/ContentGrid";
import {
  DiscoveryFilters,
  type DiscoveryFilterValues,
} from "@/components/DiscoveryFilters";
import { ErrorState } from "@/components/ErrorState";
import {
  getDiscoverContent,
  getGenres,
  getPlatforms,
} from "@/lib/api";
import type { DiscoverContentParams } from "@/types/content";

const DISCOVERY_LIMIT = 12;

type SearchParams = Record<string, string | string[] | undefined>;

type DiscoverPageProps = {
  searchParams?: Promise<SearchParams>;
};

function getSearchValue(params: SearchParams | undefined, key: string) {
  const value = params?.[key];

  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

function parseContentType(value?: string): DiscoveryFilterValues["content_type"] {
  return value === "movie" || value === "series" ? value : "";
}

function parseAvailabilityType(
  value?: string,
): DiscoveryFilterValues["availability_type"] {
  return value === "streaming" || value === "rent" || value === "buy"
    ? value
    : "";
}

function parseSort(value?: string): DiscoveryFilterValues["sort_by"] {
  return value === "top_rated" ? "top_rated" : "recent";
}

function parseOffset(value?: string) {
  const offset = Number(value);

  if (!Number.isInteger(offset) || offset < 0) {
    return 0;
  }

  return offset;
}

function buildDiscoverParams(
  filters: DiscoveryFilterValues,
  offset: number,
): DiscoverContentParams {
  return {
    content_type: filters.content_type || undefined,
    genre: filters.genre || undefined,
    platform: filters.platform || undefined,
    availability_type: filters.availability_type || undefined,
    sort_by: filters.sort_by,
    limit: DISCOVERY_LIMIT,
    offset,
  };
}

function buildPageHref(filters: DiscoveryFilterValues, offset: number) {
  const params = new URLSearchParams();

  if (filters.content_type) {
    params.set("content_type", filters.content_type);
  }

  if (filters.genre) {
    params.set("genre", filters.genre);
  }

  if (filters.platform) {
    params.set("platform", filters.platform);
  }

  if (filters.availability_type) {
    params.set("availability_type", filters.availability_type);
  }

  if (filters.sort_by !== "recent") {
    params.set("sort_by", filters.sort_by);
  }

  if (offset > 0) {
    params.set("offset", String(offset));
  }

  const query = params.toString();
  return query ? `/discover?${query}` : "/discover";
}

export default async function DiscoverPage({ searchParams }: DiscoverPageProps) {
  const params = await searchParams;
  const filters: DiscoveryFilterValues = {
    content_type: parseContentType(getSearchValue(params, "content_type")),
    genre: getSearchValue(params, "genre") || "",
    platform: getSearchValue(params, "platform") || "",
    availability_type: parseAvailabilityType(
      getSearchValue(params, "availability_type"),
    ),
    sort_by: parseSort(getSearchValue(params, "sort_by")),
  };
  const offset = parseOffset(getSearchValue(params, "offset"));

  try {
    const [genres, platforms, results] = await Promise.all([
      getGenres(),
      getPlatforms("ott"),
      getDiscoverContent(buildDiscoverParams(filters, offset)),
    ]);

    const hasPrevious = results.offset > 0;
    const hasNext = results.offset + results.limit < results.total;
    const previousOffset = Math.max(results.offset - DISCOVERY_LIMIT, 0);
    const nextOffset = results.offset + DISCOVERY_LIMIT;
    const startItem = results.total === 0 ? 0 : results.offset + 1;
    const endItem = Math.min(results.offset + results.items.length, results.total);

    return (
      <main className="discover-page">
        <section className="discover-hero">
          <span className="eyebrow">Discovery</span>
          <h1>Browse movies and series with intent.</h1>
          <p>
            Filter the current InsightStream catalog by type, genre, platform,
            availability, and decision signal.
          </p>
        </section>

        <DiscoveryFilters
          filters={filters}
          genres={genres}
          platforms={platforms}
        />

        <section className="discover-results" aria-labelledby="discover-results-heading">
          <div className="discover-results__header">
            <div>
              <span className="section-label">Results</span>
              <h2 id="discover-results-heading">Filtered catalog</h2>
            </div>
            <div className="discover-results__meta">
              <strong>{results.total}</strong>
              <span>{results.total === 1 ? "match" : "matches"}</span>
            </div>
          </div>

          <ContentGrid
            items={results.items}
            emptyMessage="No titles match these filters yet. Try clearing one or two filters."
          />

          <nav className="pagination-controls" aria-label="Discovery pagination">
            <span>
              Showing {startItem}-{endItem} of {results.total}
            </span>
            <div>
              {hasPrevious ? (
                <Link
                  className="pagination-button"
                  href={buildPageHref(filters, previousOffset)}
                >
                  Previous
                </Link>
              ) : (
                <span className="pagination-button pagination-button--disabled">
                  Previous
                </span>
              )}

              {hasNext ? (
                <Link
                  className="pagination-button"
                  href={buildPageHref(filters, nextOffset)}
                >
                  Next
                </Link>
              ) : (
                <span className="pagination-button pagination-button--disabled">
                  Next
                </span>
              )}
            </div>
          </nav>
        </section>
      </main>
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load discovery data from the backend.";

    return (
      <main className="discover-page">
        <section className="discover-hero">
          <span className="eyebrow">Discovery</span>
          <h1>Browse movies and series with intent.</h1>
          <p>
            Filter the current InsightStream catalog by type, genre, platform,
            availability, and decision signal.
          </p>
        </section>

        <ErrorState
          title="Could not load discovery"
          message={`${message} Make sure the FastAPI backend is running at the configured API URL.`}
        />
      </main>
    );
  }
}
