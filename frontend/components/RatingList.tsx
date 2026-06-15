import type { Rating } from "@/types/content";

type RatingListProps = {
  ratings: Rating[];
};

function formatReviewerGroup(group?: string | null) {
  if (!group) {
    return "General";
  }

  return group.charAt(0).toUpperCase() + group.slice(1);
}

function formatRatingCount(count?: number | null) {
  if (!count) {
    return null;
  }

  return new Intl.NumberFormat("en", {
    notation: count >= 10000 ? "compact" : "standard",
  }).format(count);
}

export function RatingList({ ratings }: RatingListProps) {
  if (ratings.length === 0) {
    return (
      <section className="detail-panel">
        <div className="detail-panel__header">
          <span className="section-label">Cross-platform signal</span>
          <h2>Ratings</h2>
        </div>
        <p className="detail-empty">No ratings are available yet.</p>
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
        {ratings.map((rating) => {
          const ratingCount = formatRatingCount(rating.rating_count);

          return (
            <article
              className={`rating-card rating-card--${rating.reviewer_group || "general"}`}
              key={`${rating.platform}-${rating.reviewer_group}-${rating.normalized_score}`}
            >
              <div>
                <h3>{rating.platform}</h3>
                <span>{formatReviewerGroup(rating.reviewer_group)}</span>
              </div>

              <strong>{Math.round(rating.normalized_score)}</strong>

              <p>
                {rating.original_score}/{rating.original_scale}
                {ratingCount ? ` • ${ratingCount} ratings` : ""}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
