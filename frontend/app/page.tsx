import { Suspense } from "react";
import { ContentSection } from "@/components/ContentSection";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { getRecentContent, getTopRatedContent } from "@/lib/api";

async function HomepageContent() {
  try {
    const [recentContent, topRatedContent] = await Promise.all([
      getRecentContent(8),
      getTopRatedContent(8),
    ]);

    return (
      <>
        <section className="catalog-summary" aria-label="Catalog summary">
          <div>
            <span className="summary-label">Catalog</span>
            <strong>{recentContent.total}</strong>
            <span>seeded titles</span>
          </div>
          <div>
            <span className="summary-label">Browse</span>
            <strong>Recent</strong>
            <span>release ordering</span>
          </div>
          <div>
            <span className="summary-label">Decision Signal</span>
            <strong>Top Rated</strong>
            <span>unified score ranking</span>
          </div>
        </section>

        <ContentSection
          title="Recent Releases"
          description="Newer movies and series from the current canonical seed data."
          items={recentContent.items}
          emptyMessage="No recent content is available yet."
        />

        <ContentSection
          title="Top Rated Picks"
          description="High-scoring titles ordered by InsightStream's unified score."
          items={topRatedContent.items}
          emptyMessage="No top-rated content is available yet."
        />
      </>
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load homepage content from the backend.";

    return (
      <ErrorState
        title="Could not load content"
        message={`${message} Make sure the FastAPI backend is running at the configured API URL.`}
      />
    );
  }
}

export default function HomePage() {
  return (
    <main>
      <section className="hero-section">
        <div className="eyebrow">Movies and series decision support</div>
        <h1>Find what is worth watching without digging through the noise.</h1>
        <p>
          InsightStream brings recent releases, top-rated titles, availability,
          ratings, and summaries into one focused entertainment dashboard.
        </p>
      </section>

      <Suspense fallback={<LoadingState message="Loading InsightStream picks..." />}>
        <HomepageContent />
      </Suspense>
    </main>
  );
}
