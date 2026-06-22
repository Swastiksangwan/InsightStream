import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { searchCatalog } from "@/lib/api";
import type {
  ContentSearchResult,
  PersonSearchResult,
  SearchResponse,
  SearchType,
} from "@/types/search";

const SEARCH_LIMIT = 12;

type SearchParams = Record<string, string | string[] | undefined>;

type SearchPageProps = {
  searchParams?: Promise<SearchParams>;
};

function getSearchValue(params: SearchParams | undefined, key: string) {
  const value = params?.[key];

  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

function parseSearchType(value?: string): SearchType {
  if (value === "content" || value === "person") {
    return value;
  }

  return "all";
}

function buildSearchHref(query: string, searchType: SearchType) {
  const params = new URLSearchParams();
  params.set("q", query);

  if (searchType !== "all") {
    params.set("type", searchType);
  }

  return `/search?${params.toString()}`;
}

function formatContentType(contentType: string) {
  return contentType === "movie"
    ? "Movie"
    : contentType === "series"
      ? "Series"
      : contentType;
}

function formatYear(value?: string | null) {
  if (!value) {
    return null;
  }

  return value.slice(0, 4);
}

function getInitials(name: string) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return initials || "IS";
}

function SearchTypeTabs({
  query,
  activeType,
}: {
  query: string;
  activeType: SearchType;
}) {
  const tabs: Array<{ label: string; value: SearchType }> = [
    { label: "All", value: "all" },
    { label: "Content", value: "content" },
    { label: "People", value: "person" },
  ];

  return (
    <nav className="search-tabs" aria-label="Search result type">
      {tabs.map((tab) => (
        <Link
          key={tab.value}
          href={buildSearchHref(query, tab.value)}
          aria-current={activeType === tab.value ? "page" : undefined}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}

function ContentResultCard({ item }: { item: ContentSearchResult }) {
  const metaItems = [
    formatYear(item.release_date),
    formatContentType(item.content_type),
    item.age_rating,
  ].filter(Boolean);

  return (
    <Link
      className="search-result-card search-result-card--content"
      href={`/content/${item.id}`}
      aria-label={`View details for ${item.title}`}
    >
      <div className="search-result-card__media search-result-card__media--poster">
        {item.poster_url ? (
          <img src={item.poster_url} alt={`${item.title} poster`} />
        ) : (
          <span>{getInitials(item.title)}</span>
        )}
      </div>

      <div className="search-result-card__body">
        <div className="search-result-card__meta">
          {metaItems.map((meta) => (
            <span key={String(meta)}>{meta}</span>
          ))}
        </div>
        <h3>{item.title}</h3>
        {item.match_reason ? (
          <span className="search-result-card__reason">{item.match_reason}</span>
        ) : null}
        <p>{item.overview_snippet || "No overview is available yet."}</p>
        {item.genres.length > 0 ? (
          <div className="search-result-card__tags">
            {item.genres.slice(0, 4).map((genre) => (
              <span key={genre}>{genre}</span>
            ))}
          </div>
        ) : null}
      </div>
    </Link>
  );
}

function PersonResultCard({ item }: { item: PersonSearchResult }) {
  return (
    <Link
      className="search-result-card search-result-card--person"
      href={`/people/${item.id}`}
      aria-label={`View person profile for ${item.name}`}
    >
      <div className="search-result-card__media search-result-card__media--avatar">
        {item.profile_url ? (
          <img src={item.profile_url} alt={`${item.name} profile`} />
        ) : (
          <span>{getInitials(item.name)}</span>
        )}
      </div>

      <div className="search-result-card__body">
        <div className="search-result-card__meta">
          <span>{item.known_for_department || "Person"}</span>
        </div>
        <h3>{item.name}</h3>
        {item.match_reason ? (
          <span className="search-result-card__reason">{item.match_reason}</span>
        ) : null}
        <p>{item.biography_snippet || "Biography not available yet."}</p>
      </div>
    </Link>
  );
}

function SearchResults({
  results,
  searchType,
}: {
  results: SearchResponse;
  searchType: SearchType;
}) {
  const showContent = searchType === "all" || searchType === "content";
  const showPeople = searchType === "all" || searchType === "person";
  const hasAnyResults =
    results.content_results.length > 0 || results.person_results.length > 0;

  if (!hasAnyResults) {
    return (
      <EmptyState
        title="No local matches"
        message="No local matches found. Missing titles or people need to be added through ingestion first."
      />
    );
  }

  return (
    <div className="search-results-stack">
      {showContent ? (
        <section className="search-results-group" aria-labelledby="search-content-heading">
          <div className="search-results-group__header">
            <div>
              <span className="section-label">Content</span>
              <h2 id="search-content-heading">Movies and series</h2>
            </div>
            <span>{results.total_content_results} matches</span>
          </div>

          {results.content_results.length > 0 ? (
            <div className="search-results-list">
              {results.content_results.map((item) => (
                <ContentResultCard item={item} key={`content-${item.id}`} />
              ))}
            </div>
          ) : (
            <p className="search-results-empty">No content matches this query.</p>
          )}
        </section>
      ) : null}

      {showPeople ? (
        <section className="search-results-group" aria-labelledby="search-people-heading">
          <div className="search-results-group__header">
            <div>
              <span className="section-label">People</span>
              <h2 id="search-people-heading">Cast and crew</h2>
            </div>
            <span>{results.total_person_results} matches</span>
          </div>

          {results.person_results.length > 0 ? (
            <div className="search-results-list">
              {results.person_results.map((item) => (
                <PersonResultCard item={item} key={`person-${item.id}`} />
              ))}
            </div>
          ) : (
            <p className="search-results-empty">No people match this query.</p>
          )}
        </section>
      ) : null}
    </div>
  );
}

export default async function SearchPage({ searchParams }: SearchPageProps) {
  const params = await searchParams;
  const query = (getSearchValue(params, "q") || "").trim();
  const searchType = parseSearchType(getSearchValue(params, "type"));

  if (!query) {
    return (
      <main className="search-page">
        <section className="search-hero">
          <span className="eyebrow">Local Search</span>
          <h1>Search the InsightStream catalog.</h1>
          <p>
            Find ingested movies, series, cast, directors, creators, and crew
            from the local database.
          </p>
        </section>

        <EmptyState
          title="Start with a title or name"
          message="Use the search box in the navigation bar to search local catalog metadata."
        />
      </main>
    );
  }

  try {
    const results = await searchCatalog(query, searchType, SEARCH_LIMIT);

    return (
      <main className="search-page">
        <section className="search-hero">
          <span className="eyebrow">Local Search</span>
          <h1>Results for “{results.query}”</h1>
          <p>
            Showing local database matches from the InsightStream catalog. Results
            can match titles, genres, people, credits, and biographies. Missing
            titles need to be added through ingestion first.
          </p>
        </section>

        <SearchTypeTabs query={results.query} activeType={searchType} />
        <SearchResults results={results} searchType={searchType} />
      </main>
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load search results from the backend.";

    return (
      <main className="search-page">
        <section className="search-hero">
          <span className="eyebrow">Local Search</span>
          <h1>Search results</h1>
          <p>Search the local InsightStream catalog.</p>
        </section>

        <ErrorState
          title="Could not load search"
          message={`${message} Make sure the FastAPI backend is running at the configured API URL.`}
        />
      </main>
    );
  }
}
