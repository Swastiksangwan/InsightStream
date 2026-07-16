import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { ErrorState } from "@/components/ErrorState";
import { searchCatalog } from "@/lib/api";
import type {
  ContentSearchResult,
  PersonSearchResult,
  SearchResponse,
  SearchType,
} from "@/types/search";

const SEARCH_LIMIT = 18;

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
  return value === "person" ? "person" : "content";
}

function buildSearchHref(query: string, searchType: SearchType) {
  const params = new URLSearchParams();

  if (query) {
    params.set("q", query);
  }

  if (searchType === "person") {
    params.set("type", searchType);
  }

  const queryString = params.toString();
  return queryString ? `/search?${queryString}` : "/search";
}

function formatContentType(contentType: string) {
  return contentType === "movie"
    ? "Movie"
    : contentType === "series"
      ? "Series"
      : contentType;
}

function formatYear(item: ContentSearchResult) {
  const value = item.release_date || item.latest_activity_date;

  if (!value) {
    return null;
  }

  return value.slice(0, 4);
}

function getInitials(value: string) {
  const initials = value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return initials || "IS";
}

function getVisibleTotal(results: SearchResponse, searchType: SearchType) {
  if (searchType === "person") {
    return results.total_person_results;
  }

  return results.total_content_results;
}

function formatResultCount(count: number) {
  return `${count} ${count === 1 ? "result" : "results"}`;
}

function getTitleMarqueeStyle(title: string): CSSProperties | undefined {
  if (title.length <= 22) {
    return undefined;
  }

  const titleSlideDistance = Math.min(190, Math.max(34, title.length * 7 - 160));

  return {
    "--home-title-slide-distance": `-${titleSlideDistance}px`,
  } as CSSProperties;
}

function SearchTypeTabs({
  query,
  activeType,
}: {
  query: string;
  activeType: SearchType;
}) {
  const tabs: Array<{ label: string; value: SearchType }> = [
    { label: "Titles", value: "content" },
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
  const metaItems = [formatYear(item), formatContentType(item.content_type)].filter(
    Boolean,
  );
  const titleStyle = getTitleMarqueeStyle(item.title);
  const isLongTitle = Boolean(titleStyle);

  return (
    <Link
      className="search-title-card"
      href={`/content/${item.id}`}
      aria-label={`View details for ${item.title}`}
    >
      <div className="search-title-card__poster">
        {item.poster_url ? (
          <img src={item.poster_url} alt={`${item.title} poster`} />
        ) : (
          <div className="search-title-card__fallback" aria-hidden="true">
            <span>{getInitials(item.title)}</span>
          </div>
        )}
      </div>

      <div className="search-title-card__body">
        <h3 title={item.title}>
          <span
            className={isLongTitle ? "home-title-marquee" : undefined}
            style={titleStyle}
          >
            {item.title}
          </span>
        </h3>
        {metaItems.length > 0 ? (
          <div className="search-title-card__meta">
            {metaItems.map((meta) => (
              <span key={String(meta)}>{meta}</span>
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
      className="search-person-card"
      href={`/people/${item.id}`}
      aria-label={`View person profile for ${item.name}`}
    >
      <div className="search-person-card__avatar">
        {item.profile_url ? (
          <img src={item.profile_url} alt={`${item.name} profile`} />
        ) : (
          <span>{getInitials(item.name)}</span>
        )}
      </div>
      <div className="search-person-card__copy">
        <h3>{item.name}</h3>
        {item.known_for_department ? <p>{item.known_for_department}</p> : null}
      </div>
    </Link>
  );
}

function SearchEmpty({ query }: { query?: string }) {
  return (
    <section className="search-empty" aria-live="polite">
      <h2>{query ? `No results for “${query}”` : "Search the catalog"}</h2>
      <p>
        {query
          ? "Try another title or person name from the InsightStream catalog."
          : "Use the search field above to find titles or people in InsightStream."}
      </p>
    </section>
  );
}

function ResultSection({
  title,
  query,
  count,
  children,
}: {
  title: string;
  query: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section className="search-results-section" aria-labelledby={`search-${title}`}>
      <div className="search-results-section__header">
        <h1 id={`search-${title}`}>
          {title} matching “{query}”
        </h1>
        <span>{formatResultCount(count)}</span>
      </div>
      {children}
    </section>
  );
}

function SearchResults({
  results,
  searchType,
}: {
  results: SearchResponse;
  searchType: SearchType;
}) {
  const showContent = searchType === "content";
  const showPeople = searchType === "person";
  const visibleTotal = getVisibleTotal(results, searchType);

  if (visibleTotal === 0) {
    return <SearchEmpty query={results.query} />;
  }

  return (
    <div className="search-results-stack">
      {showContent && results.content_results.length > 0 ? (
        <ResultSection
          title="Titles"
          query={results.query}
          count={results.total_content_results}
        >
          <div className="search-title-grid">
            {results.content_results.map((item) => (
              <ContentResultCard item={item} key={`content-${item.id}`} />
            ))}
          </div>
        </ResultSection>
      ) : null}

      {showPeople && results.person_results.length > 0 ? (
        <ResultSection
          title="People"
          query={results.query}
          count={results.total_person_results}
        >
          <div className="search-people-grid">
            {results.person_results.map((item) => (
              <PersonResultCard item={item} key={`person-${item.id}`} />
            ))}
          </div>
        </ResultSection>
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
        <section className="search-panel">
          <SearchTypeTabs query="" activeType={searchType} />
          <SearchEmpty />
        </section>
      </main>
    );
  }

  try {
    const results = await searchCatalog(query, searchType, SEARCH_LIMIT);

    return (
      <main className="search-page">
        <section className="search-panel">
          <SearchTypeTabs query={results.query} activeType={searchType} />
          <SearchResults results={results} searchType={searchType} />
        </section>
      </main>
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load search results from the backend.";

    return (
      <main className="search-page">
        <section className="search-panel">
          <SearchTypeTabs query={query} activeType={searchType} />
          <ErrorState title="Could not load search" message={message} />
        </section>
      </main>
    );
  }
}
