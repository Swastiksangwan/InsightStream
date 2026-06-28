import type { RatingSourceItem, RatingsResponse } from "@/types/content";

type RatingListProps = {
  ratings: RatingsResponse;
};

function formatSourceCategory(category?: string | null) {
  if (!category) {
    return "Rating";
  }

  return category.charAt(0).toUpperCase() + category.slice(1);
}

function formatVoteCount(source: RatingSourceItem) {
  if (source.rating_count_label) {
    return source.rating_count_label;
  }

  const count = source.vote_count;
  if (!count) {
    return null;
  }

  return new Intl.NumberFormat("en", {
    notation: count >= 10000 ? "compact" : "standard",
  }).format(count);
}

function formatScore(value?: number | null) {
  if (value === null || value === undefined) {
    return null;
  }

  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatRawRating(source: RatingSourceItem) {
  const rawScore = formatScore(source.raw_score);
  const rawScale = formatScore(source.raw_score_scale);

  if (!rawScore || !rawScale) {
    return null;
  }

  return `${rawScore}/${rawScale}`;
}

function isLetterboxdSource(source: RatingSourceItem) {
  return source.source_name.toLowerCase() === "letterboxd";
}

function formatSourceLabel(source: RatingSourceItem) {
  const baseLabel = isLetterboxdSource(source)
    ? "Film-community signal · Snapshot source"
    : formatSourceCategory(source.source_category);

  return `${baseLabel}${source.rating_url ? " · Open source page" : ""}`;
}

function getScoringSources(ratings: RatingsResponse) {
  const explicitSources = (ratings.sources ?? []).filter(
    (source) => source.included_in_unified_score,
  );

  if (explicitSources.length > 0) {
    return explicitSources;
  }

  const fallbackCount =
    ratings.scoring_source_count ??
    (ratings.unified_score === null || ratings.unified_score === undefined
      ? 0
      : ratings.source_count);

  if (fallbackCount <= 0) {
    return [];
  }

  return (ratings.sources ?? [])
    .filter((source) => !isLetterboxdSource(source) && (source.vote_count ?? 0) >= 50)
    .slice(0, fallbackCount);
}

function getScoringSourceCount(ratings: RatingsResponse) {
  if (ratings.scoring_source_count !== undefined) {
    return ratings.scoring_source_count;
  }

  return getScoringSources(ratings).length;
}

function getInsightSourceLabel(ratings: RatingsResponse) {
  const scoringSourceCount = getScoringSourceCount(ratings);

  if (ratings.unified_score === null || ratings.unified_score === undefined) {
    return scoringSourceCount > 0
      ? `${scoringSourceCount} scoring source${scoringSourceCount === 1 ? "" : "s"}`
      : "Source ratings available";
  }

  return `${scoringSourceCount} scoring source${scoringSourceCount === 1 ? "" : "s"}`;
}

function getInsightCopy(ratings: RatingsResponse) {
  const scoringSourceCount = getScoringSourceCount(ratings);
  const scoringSourceNames = getScoringSources(ratings)
    .map((source) => source.display_name)
    .filter(Boolean);

  if (ratings.unified_score === null || ratings.unified_score === undefined) {
    return "Source ratings available, but not enough vote-backed data for a score yet.";
  }

  if (scoringSourceCount === 1) {
    return "Based on one vote-backed source.";
  }

  if (scoringSourceNames.length >= 2) {
    return `${scoringSourceNames.slice(0, 2).join(" + ")} vote-backed average.`;
  }

  return "Vote-backed rating average.";
}

export function RatingList({ ratings }: RatingListProps) {
  const sources = ratings?.sources ?? [];

  if (sources.length === 0) {
    return (
      <section className="detail-panel">
        <div className="detail-panel__header">
          <span className="section-label">Cross-platform signal</span>
          <h2>Ratings</h2>
        </div>
        <p className="detail-empty">Not enough rating data yet.</p>
      </section>
    );
  }

  return (
    <section className="detail-panel">
      <div className="detail-panel__header">
        <span className="section-label">Cross-platform signal</span>
        <h2>Ratings</h2>
      </div>

      <div className="rating-list">
        <article className="rating-card rating-card--insight">
          <div>
            <h3>InsightStream Score</h3>
            <span>{getInsightSourceLabel(ratings)}</span>
          </div>

          <strong>{ratings.unified_score ?? "--"}</strong>

          <p>{getInsightCopy(ratings)}</p>
        </article>

        {sources.map((source) => {
          const voteCount = formatVoteCount(source);
          const rawRating = formatRawRating(source);
          const isLetterboxd = isLetterboxdSource(source);
          const cardClassName = `rating-card rating-card--${source.source_category || "general"}${
            source.rating_url ? " rating-card--link" : ""
          }${isLetterboxd ? " rating-card--snapshot" : ""}`;
          const cardContent = (
            <>
              <div>
                <h3>{source.display_name}</h3>
                <span>{formatSourceLabel(source)}</span>
              </div>

              <strong>
                {isLetterboxd
                  ? rawRating ?? "--"
                  : source.normalized_score === null || source.normalized_score === undefined
                    ? "--"
                    : Math.round(source.normalized_score)}
              </strong>

              <p>
                {isLetterboxd
                  ? "Snapshot rating; live score may differ."
                  : `${rawRating ?? "Rating scale unavailable"}${voteCount ? ` · ${voteCount}` : ""}`}
              </p>
            </>
          );

          if (source.rating_url) {
            return (
              <a
                aria-label={`Open ${source.display_name} rating page`}
                className={cardClassName}
                href={source.rating_url}
                key={`${source.source_name}-${source.normalized_score}`}
                rel="noopener noreferrer"
                target="_blank"
              >
                {cardContent}
              </a>
            );
          }

          return (
            <article
              className={cardClassName}
              key={`${source.source_name}-${source.normalized_score}`}
            >
              {cardContent}
            </article>
          );
        })}
      </div>
    </section>
  );
}
