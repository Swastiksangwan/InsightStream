import type { SeriesMetadata } from "@/types/content";

type SeriesInfoPanelProps = {
  seriesMetadata?: SeriesMetadata | null;
};

function titleCaseStatus(status?: string | null) {
  if (!status) {
    return null;
  }

  return status
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDate(dateValue?: string | null) {
  if (!dateValue) {
    return null;
  }

  const parsed = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return dateValue;
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

function seasonText(count: number) {
  return `${count} season${count === 1 ? "" : "s"}`;
}

function nextSeasonValue(seriesMetadata: SeriesMetadata) {
  const seasonNumber = seriesMetadata.next_season_number;
  if (!seasonNumber) {
    return seriesMetadata.season_summary_note || null;
  }

  const airDate = formatDate(seriesMetadata.next_season_air_date);
  if (airDate) {
    return `Season ${seasonNumber} · ${airDate}`;
  }

  if (seriesMetadata.next_season_year) {
    return `Season ${seasonNumber} · ${seriesMetadata.next_season_year}`;
  }

  return `Season ${seasonNumber}`;
}

export function SeriesInfoPanel({ seriesMetadata }: SeriesInfoPanelProps) {
  if (!seriesMetadata) {
    return null;
  }

  const status =
    titleCaseStatus(seriesMetadata.series_status_normalized) ||
    seriesMetadata.series_status;
  const lastAired =
    formatDate(seriesMetadata.last_episode_air_date) ||
    formatDate(seriesMetadata.last_air_date);
  const nextEpisode = formatDate(seriesMetadata.next_episode_air_date);
  const firstAired = formatDate(seriesMetadata.first_air_date);
  const hasAnnouncedSeason = Boolean(seriesMetadata.has_announced_season);
  const releasedSeasonCount = seriesMetadata.released_seasons_count;
  const nextSeason = hasAnnouncedSeason ? nextSeasonValue(seriesMetadata) : null;
  const showReleasedSeasons =
    hasAnnouncedSeason && typeof releasedSeasonCount === "number";
  const showTotalSeasons =
    !showReleasedSeasons && typeof seriesMetadata.number_of_seasons === "number";

  const rows = [
    status ? { label: "Status", value: status } : null,
    showReleasedSeasons
      ? { label: "Released seasons", value: seasonText(releasedSeasonCount) }
      : null,
    nextSeason
      ? {
          label:
            seriesMetadata.next_season_air_date || seriesMetadata.next_season_year
              ? "Next season"
              : "Announced season",
          value: nextSeason,
        }
      : null,
    showTotalSeasons
      ? {
          label: "Seasons",
          value: seasonText(seriesMetadata.number_of_seasons || 0),
        }
      : null,
    seriesMetadata.number_of_episodes
      ? { label: "Episodes", value: String(seriesMetadata.number_of_episodes) }
      : null,
    firstAired ? { label: "First aired", value: firstAired } : null,
    lastAired ? { label: "Last aired", value: lastAired } : null,
    nextEpisode ? { label: "Next episode", value: nextEpisode } : null,
  ].filter((row): row is { label: string; value: string } => Boolean(row));

  if (rows.length === 0) {
    return null;
  }

  return (
    <section className="detail-panel series-info" aria-label="Series lifecycle metadata">
      <div className="detail-panel__header">
        <span className="section-label">Series info</span>
        <h2>Lifecycle</h2>
      </div>

      <dl className="series-info__grid">
        {rows.map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
