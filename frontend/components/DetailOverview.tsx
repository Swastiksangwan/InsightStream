import Link from "next/link";
import type { Content } from "@/types/content";

type DetailOverviewProps = {
  content: Content;
  genres: string[];
};

function buildGenreHref(genre: string) {
  const params = new URLSearchParams({ genre });
  return `/discover?${params.toString()}`;
}

export function DetailOverview({ content, genres }: DetailOverviewProps) {
  return (
    <section className="detail-overview" aria-labelledby="detail-overview-heading">
      <div className="detail-section-heading">
        <h2 id="detail-overview-heading">Overview</h2>
      </div>

      <p>{content.overview || "No overview is available yet."}</p>

      {genres.length > 0 ? (
        <div className="genre-chip-list" aria-label="Genres">
          {genres.map((genre) => (
            <Link key={genre} href={buildGenreHref(genre)}>
              {genre}
            </Link>
          ))}
        </div>
      ) : null}
    </section>
  );
}
