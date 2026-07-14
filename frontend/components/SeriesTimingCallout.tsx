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

const ACTIVE_AIRING_LOOKBACK_DAYS = 45;
const NEXT_EPISODE_SOON_DAYS = 21;

const ACTIVE_SERIES_STATUSES = new Set([
  "in production",
  "ongoing",
  "returning",
  "returning series",
  "upcoming",
]);
const INACTIVE_SERIES_STATUSES = new Set([
  "canceled",
  "cancelled",
  "ended",
  "finished",
]);

type SeriesTimingMode = {
  heading: string;
  primaryLine: string;
  secondaryLine?: string | null;
};

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

function dayDifferenceFromReference(
  dateValue?: string | null,
  referenceDate = new Date(),
) {
  const parts = parseDateOnly(dateValue);
  if (!parts) {
    return null;
  }

  const today = new Date(
    referenceDate.getFullYear(),
    referenceDate.getMonth(),
    referenceDate.getDate(),
  );
  const target = dateFromParts(parts);
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  return Math.round((target.getTime() - today.getTime()) / millisecondsPerDay);
}

function compareDateValues(
  leftDateValue?: string | null,
  rightDateValue?: string | null,
) {
  const leftParts = parseDateOnly(leftDateValue);
  const rightParts = parseDateOnly(rightDateValue);
  if (!leftParts || !rightParts) {
    return null;
  }

  return dateFromParts(leftParts).getTime() - dateFromParts(rightParts).getTime();
}

function nextEpisodeLine(dateValue?: string | null, referenceDate = new Date()) {
  const difference = dayDifferenceFromReference(dateValue, referenceDate);
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

function seasonPremiereLine(dateValue?: string | null) {
  const formatted = formatDate(dateValue);
  return formatted ? `Premieres ${formatted}.` : null;
}

function nextSeasonLine(seriesMetadata: SeriesMetadata) {
  const seasonNumber = seriesMetadata.next_season_number;
  const fullDate = formatDate(seriesMetadata.next_season_air_date);
  const releasedSeasons = seriesMetadata.released_seasons_count;
  const announcedSeasons = seriesMetadata.announced_seasons_count;

  if (seasonNumber && fullDate) {
    return `Season ${seasonNumber} premieres ${fullDate}.`;
  }

  if (seasonNumber && seriesMetadata.next_season_year) {
    return `Season ${seasonNumber} expected in ${seriesMetadata.next_season_year}.`;
  }

  if (fullDate) {
    return `Premieres ${fullDate}.`;
  }

  if (seasonNumber) {
    return `Season ${seasonNumber} announced.`;
  }

  if (seriesMetadata.has_announced_season) {
    return "Next season announced.";
  }

  if (
    releasedSeasons !== null &&
    releasedSeasons !== undefined &&
    announcedSeasons !== null &&
    announcedSeasons !== undefined &&
    announcedSeasons > releasedSeasons
  ) {
    return "Next season announced.";
  }

  return null;
}

function hasAnnouncedSeasonSignal(seriesMetadata: SeriesMetadata) {
  const releasedSeasons = seriesMetadata.released_seasons_count;
  const announcedSeasons = seriesMetadata.announced_seasons_count;
  const nextSeasonNumber = seriesMetadata.next_season_number;

  return Boolean(
    seriesMetadata.next_season_air_date ||
      seriesMetadata.next_season_number ||
      seriesMetadata.next_season_year ||
      seriesMetadata.has_announced_season ||
      (releasedSeasons !== null &&
        releasedSeasons !== undefined &&
        announcedSeasons !== null &&
        announcedSeasons !== undefined &&
        announcedSeasons > releasedSeasons) ||
      (releasedSeasons !== null &&
        releasedSeasons !== undefined &&
        nextSeasonNumber !== null &&
        nextSeasonNumber !== undefined &&
        nextSeasonNumber > releasedSeasons),
  );
}

function isInactiveStatus(status?: string | null) {
  return Boolean(status && INACTIVE_SERIES_STATUSES.has(status));
}

export function getSeriesTimingMode(
  seriesMetadata: SeriesMetadata,
  referenceDate = new Date(),
): SeriesTimingMode | null {
  const status = normalizeStatus(
    seriesMetadata.series_status_normalized || seriesMetadata.series_status,
  );
  const hasActiveStatus = Boolean(status && ACTIVE_SERIES_STATUSES.has(status));
  const hasInactiveStatus = isInactiveStatus(status);
  const lastEpisodeDate =
    seriesMetadata.last_episode_air_date || seriesMetadata.last_air_date;
  const nextEpisodeDifference = dayDifferenceFromReference(
    seriesMetadata.next_episode_air_date,
    referenceDate,
  );
  const lastEpisodeDifference = dayDifferenceFromReference(
    lastEpisodeDate,
    referenceDate,
  );
  const nextSeasonDifference = dayDifferenceFromReference(
    seriesMetadata.next_season_air_date,
    referenceDate,
  );
  const lastEpisodeSeasonComparison = compareDateValues(
    lastEpisodeDate,
    seriesMetadata.next_season_air_date,
  );
  const nextEpisodeSeasonComparison = compareDateValues(
    seriesMetadata.next_episode_air_date,
    seriesMetadata.next_season_air_date,
  );
  const lastEpisodeIsFromAnnouncedSeason =
    lastEpisodeSeasonComparison !== null && lastEpisodeSeasonComparison >= 0;
  const nextEpisodeIsSeasonPremiere = nextEpisodeSeasonComparison === 0;
  const hasAnnouncedSeason = hasAnnouncedSeasonSignal(seriesMetadata);
  const isNextEpisodeUpcoming =
    nextEpisodeDifference !== null && nextEpisodeDifference >= 0;
  const isNextSeasonUpcoming =
    nextSeasonDifference !== null && nextSeasonDifference >= 0;
  const isNextSeasonYearUpcoming =
    seriesMetadata.next_season_year !== null &&
    seriesMetadata.next_season_year !== undefined &&
    seriesMetadata.next_season_year >= referenceDate.getFullYear();
  const hasUndatedSeasonAnnouncement =
    hasAnnouncedSeason && !seriesMetadata.next_season_air_date;
  const hasUpcomingDate =
    isNextEpisodeUpcoming ||
    isNextSeasonUpcoming ||
    isNextSeasonYearUpcoming ||
    hasUndatedSeasonAnnouncement;
  const isNextEpisodeSoon =
    isNextEpisodeUpcoming &&
    nextEpisodeDifference <= NEXT_EPISODE_SOON_DAYS;
  const isLastEpisodeRecent =
    lastEpisodeDifference !== null &&
    lastEpisodeDifference <= 0 &&
    Math.abs(lastEpisodeDifference) <= ACTIVE_AIRING_LOOKBACK_DAYS;

  if (hasInactiveStatus && !hasUpcomingDate) {
    return null;
  }

  if (
    hasAnnouncedSeason &&
    !lastEpisodeIsFromAnnouncedSeason &&
    (nextSeasonDifference === null || isNextSeasonUpcoming)
  ) {
    const seasonLine =
      seasonPremiereLine(seriesMetadata.next_season_air_date) ||
      ((nextEpisodeIsSeasonPremiere ||
        isNextEpisodeUpcoming)
        ? seasonPremiereLine(seriesMetadata.next_episode_air_date)
        : null) ||
      nextSeasonLine(seriesMetadata);

    return seasonLine
      ? {
          heading: seriesMetadata.next_season_air_date
            ? "New season coming"
            : "Next season",
          primaryLine: seasonLine,
        }
      : null;
  }

  if (
    hasAnnouncedSeason &&
    !lastEpisodeIsFromAnnouncedSeason &&
    nextSeasonDifference !== null &&
    nextSeasonDifference < 0
  ) {
    return null;
  }

  if (
    hasAnnouncedSeason &&
    lastEpisodeIsFromAnnouncedSeason &&
    !seriesMetadata.next_episode_air_date
  ) {
    return null;
  }

  if (
    isNextEpisodeSoon &&
    seriesMetadata.next_episode_air_date &&
    !(nextEpisodeIsSeasonPremiere && !lastEpisodeIsFromAnnouncedSeason)
  ) {
    const episodeLine =
      nextEpisodeLine(seriesMetadata.next_episode_air_date, referenceDate);

    if (!episodeLine) {
      return null;
    }

    return {
      heading: "Airing now",
      primaryLine: episodeLine,
      secondaryLine:
        isNextEpisodeSoon && lastEpisodeDate
          ? latestEpisodeLine(lastEpisodeDate)
          : null,
    };
  }

  if (
    !seriesMetadata.next_episode_air_date &&
    isLastEpisodeRecent &&
    !hasAnnouncedSeason &&
    !hasInactiveStatus &&
    hasActiveStatus
  ) {
    const recentLine = latestEpisodeLine(lastEpisodeDate);
    return recentLine
      ? {
          heading: "Recently aired",
          primaryLine: recentLine,
        }
      : null;
  }

  const seasonLine =
    hasUndatedSeasonAnnouncement || isNextSeasonUpcoming || isNextEpisodeUpcoming
      ? (hasUndatedSeasonAnnouncement || isNextSeasonUpcoming
          ? nextSeasonLine(seriesMetadata)
          : null) ||
        (isNextEpisodeUpcoming
          ? seasonPremiereLine(seriesMetadata.next_episode_air_date)
          : null)
      : null;
  if (seasonLine) {
    return {
      heading: hasActiveStatus ? "Next season" : "Season update",
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

  const mode = getSeriesTimingMode(seriesMetadata);

  if (!mode) {
    return null;
  }

  return (
    <section
      className="series-timing-callout"
      aria-label="Series release timing"
    >
      <span className="series-timing-callout__label">Update</span>
      <div>
        <h2>{mode.heading}</h2>
        <p className="series-timing-callout__primary">{mode.primaryLine}</p>
        {mode.secondaryLine ? (
          <p className="series-timing-callout__secondary">
            {mode.secondaryLine}
          </p>
        ) : null}
      </div>
    </section>
  );
}
