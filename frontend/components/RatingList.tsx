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

function getInsightCopy(ratings: RatingsResponse) {
  if (ratings.unified_score === null || ratings.unified_score === undefined) {
    return "Source ratings available, but not enough votes for an InsightStream Score yet.";
  }

  if (ratings.source_count === 1) {
    return "Based on the available TMDb audience rating.";
  }

  return "Weighted from available trusted rating sources.";
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
            <span>{ratings.source_count} source{ratings.source_count === 1 ? "" : "s"}</span>
          </div>

          <strong>{ratings.unified_score ?? "--"}</strong>

          <p>{getInsightCopy(ratings)}</p>
        </article>

        {sources.map((source) => {
          const voteCount = formatVoteCount(source);
          const rawRating = formatRawRating(source);
          const cardClassName = `rating-card rating-card--${source.source_category || "general"}${
            source.rating_url ? " rating-card--link" : ""
          }`;
          const cardContent = (
            <>
              <div>
                <h3>{source.display_name}</h3>
                <span>
                  {formatSourceCategory(source.source_category)}
                  {source.rating_url ? " · Source page" : ""}
                </span>
              </div>

              <strong>
                {source.normalized_score === null || source.normalized_score === undefined
                  ? "--"
                  : Math.round(source.normalized_score)}
              </strong>

              <p>
                {rawRating ?? "Rating scale unavailable"}
                {voteCount ? ` · ${voteCount}` : ""}
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
