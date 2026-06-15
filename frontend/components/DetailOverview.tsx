import type { Content } from "@/types/content";

type DetailOverviewProps = {
  content: Content;
  genres: string[];
};

export function DetailOverview({ content, genres }: DetailOverviewProps) {
  return (
    <section className="detail-overview" aria-labelledby="detail-overview-heading">
      <div className="detail-section-heading">
        <span className="section-label">Story</span>
        <h2 id="detail-overview-heading">Overview</h2>
      </div>

      <p>{content.overview || "No overview is available yet."}</p>

      {genres.length > 0 ? (
        <div className="genre-chip-list" aria-label="Genres">
          {genres.map((genre) => (
            <span key={genre}>{genre}</span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
