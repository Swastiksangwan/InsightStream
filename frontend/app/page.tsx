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
            <strong>{recentContent.total} titles</strong>
            <span>movies and series ready for browsing</span>
          </div>
          <div>
            <span className="summary-label">Browse</span>
            <strong>Recent</strong>
            <span>release-date discovery feed</span>
          </div>
          <div>
            <span className="summary-label">Decision Signal</span>
            <strong>Top Rated</strong>
            <span>ranked by unified score</span>
          </div>
        </section>

        <ContentSection
          title="Recent Releases"
          eyebrow="Fresh from the catalog"
          description="Newer movies and series from the current canonical seed data."
          items={recentContent.items}
          emptyMessage="No recent content is available yet."
        />

        <ContentSection
          title="Top Rated Picks"
          eyebrow="Decision support"
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
        <h1>Decide what to watch next.</h1>
        <p>
          Browse recent releases and top-rated picks with a clean, data-first
          view of entertainment signals.
        </p>
      </section>

      <Suspense fallback={<LoadingState message="Loading InsightStream picks..." />}>
        <HomepageContent />
      </Suspense>
    </main>
  );
}
