import type { Content, SeriesMetadata } from "@/types/content";

type SeriesTimingCalloutProps = {
  contentType: Content["type"];
  seriesMetadata?: SeriesMetadata | null;
};

type DateParts = {
  year: number;
  month: number;
  day: number;
};

const ACTIVE_SERIES_STATUSES = new Set(["ongoing", "upcoming"]);

function normalizeStatus(status?: string | null) {
  return status?.trim().toLowerCase() || null;
}

function parseDateOnly(dateValue?: string | null): DateParts | null {
  if (!dateValue) {
    return null;
  }

  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateValue);
  if (!match) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!year || month < 1 || month > 12 || day < 1 || day > 31) {
    return null;
  }

  return { year, month, day };
}

function dateFromParts(parts: DateParts) {
  return new Date(parts.year, parts.month - 1, parts.day);
}

function formatDate(dateValue?: string | null) {
  const parts = parseDateOnly(dateValue);
  if (!parts) {
    return null;
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(dateFromParts(parts));
}

function dayDifferenceFromToday(dateValue?: string | null) {
  const parts = parseDateOnly(dateValue);
  if (!parts) {
    return null;
  }

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = dateFromParts(parts);
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  return Math.round((target.getTime() - today.getTime()) / millisecondsPerDay);
}

function nextEpisodeLine(dateValue?: string | null) {
  const difference = dayDifferenceFromToday(dateValue);
  if (difference === null) {
    return null;
  }

  if (difference === 0) {
    return "New episode today.";
  }

  if (difference === 1) {
    return "Next episode tomorrow.";
  }

  const formatted = formatDate(dateValue);
  return formatted ? `Next episode on ${formatted}.` : null;
}

function latestEpisodeLine(dateValue?: string | null) {
  const formatted = formatDate(dateValue);
  return formatted ? `Latest episode aired ${formatted}.` : null;
}

function nextSeasonLine(seriesMetadata: SeriesMetadata) {
  const seasonNumber = seriesMetadata.next_season_number;
  const fullDate = formatDate(seriesMetadata.next_season_air_date);

  if (seasonNumber && fullDate) {
    return `Season ${seasonNumber} expected ${fullDate}.`;
  }

  if (seasonNumber && seriesMetadata.next_season_year) {
    return `Season ${seasonNumber} expected in ${seriesMetadata.next_season_year}.`;
  }

  if (fullDate) {
    return `Next season expected ${fullDate}.`;
  }

  if (seasonNumber) {
    return `Season ${seasonNumber} announced.`;
  }

  return null;
}

function timingMode(seriesMetadata: SeriesMetadata) {
  const episodeLine = nextEpisodeLine(seriesMetadata.next_episode_air_date);
  if (episodeLine) {
    return {
      heading: "Airing now",
      primaryLine: episodeLine,
    };
  }

  const seasonLine = nextSeasonLine(seriesMetadata);
  if (seasonLine) {
    return {
      heading: "Season update",
      primaryLine: seasonLine,
    };
  }

  return null;
}

export function SeriesTimingCallout({
  contentType,
  seriesMetadata,
}: SeriesTimingCalloutProps) {
  if (contentType !== "series" || !seriesMetadata) {
    return null;
  }

  const status = normalizeStatus(
    seriesMetadata.series_status_normalized || seriesMetadata.series_status,
  );
  if (!status || !ACTIVE_SERIES_STATUSES.has(status)) {
    return null;
  }

  const mode = timingMode(seriesMetadata);
  const secondaryLine = latestEpisodeLine(seriesMetadata.last_episode_air_date);

  if (!mode) {
    return null;
  }

  return (
    <section
      className="series-timing-callout"
      aria-label="Series release timing"
    >
      <span className="series-timing-callout__label">Series timing</span>
      <div>
        <h2>{mode.heading}</h2>
        <p className="series-timing-callout__primary">{mode.primaryLine}</p>
        {secondaryLine ? (
          <p className="series-timing-callout__secondary">{secondaryLine}</p>
        ) : null}
      </div>
    </section>
  );
}
