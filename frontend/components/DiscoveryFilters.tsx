"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import type { Genre, PlatformMetadata } from "@/types/content";

export type DiscoveryFilterValues = {
  content_type: "" | "movie" | "series";
  genre: string;
  platform: string;
  availability_type: "" | "streaming" | "rent" | "buy";
  sort_by: "recent" | "top_rated";
};

type DiscoveryFiltersProps = {
  filters: DiscoveryFilterValues;
  genres: Genre[];
  platforms: PlatformMetadata[];
};

function buildDiscoverPath(filters: DiscoveryFilterValues) {
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

  const query = params.toString();
  return query ? `/discover?${query}` : "/discover";
}

function hasActiveFilters(filters: DiscoveryFilterValues) {
  return Boolean(
    filters.content_type ||
      filters.genre ||
      filters.platform ||
      filters.availability_type ||
      filters.sort_by !== "recent",
  );
}

export function DiscoveryFilters({
  filters,
  genres,
  platforms,
}: DiscoveryFiltersProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  function updateFilters(nextFilters: DiscoveryFilterValues) {
    startTransition(() => {
      router.push(buildDiscoverPath(nextFilters));
    });
  }

  function resetFilters() {
    startTransition(() => {
      router.push("/discover");
    });
  }

  return (
    <form className="discovery-filters" aria-label="Discovery filters">
      <div className="discovery-filters__header">
        <div>
          <span className="section-label">Browse controls</span>
          <h2>Filter the catalog</h2>
        </div>
        <button
          type="button"
          className="secondary-action"
          onClick={resetFilters}
          disabled={isPending || !hasActiveFilters(filters)}
        >
          Clear filters
        </button>
      </div>

      <div className="discovery-filters__grid">
        <label>
          <span>Content Type</span>
          <select
            value={filters.content_type}
            onChange={(event) =>
              updateFilters({
                ...filters,
                content_type: event.target.value as DiscoveryFilterValues["content_type"],
              })
            }
            disabled={isPending}
          >
            <option value="">All</option>
            <option value="movie">Movie</option>
            <option value="series">Series</option>
          </select>
        </label>

        <label>
          <span>Genre</span>
          <select
            value={filters.genre}
            onChange={(event) =>
              updateFilters({ ...filters, genre: event.target.value })
            }
            disabled={isPending}
          >
            <option value="">All genres</option>
            {genres.map((genre) => (
              <option key={genre.id} value={genre.name}>
                {genre.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Platform</span>
          <select
            value={filters.platform}
            onChange={(event) =>
              updateFilters({ ...filters, platform: event.target.value })
            }
            disabled={isPending}
          >
            <option value="">All platforms</option>
            {platforms.map((platform) => (
              <option key={platform.id} value={platform.name}>
                {platform.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Availability</span>
          <select
            value={filters.availability_type}
            onChange={(event) =>
              updateFilters({
                ...filters,
                availability_type: event.target
                  .value as DiscoveryFilterValues["availability_type"],
              })
            }
            disabled={isPending}
          >
            <option value="">Any</option>
            <option value="streaming">Streaming</option>
            <option value="rent">Rent</option>
            <option value="buy">Buy</option>
          </select>
        </label>

        <label>
          <span>Sort</span>
          <select
            value={filters.sort_by}
            onChange={(event) =>
              updateFilters({
                ...filters,
                sort_by: event.target.value as DiscoveryFilterValues["sort_by"],
              })
            }
            disabled={isPending}
          >
            <option value="recent">Recent</option>
            <option value="top_rated">Top Rated</option>
          </select>
        </label>
      </div>

      {isPending ? (
        <p className="discovery-filters__status" role="status">
          Updating results...
        </p>
      ) : null}
    </form>
  );
}
