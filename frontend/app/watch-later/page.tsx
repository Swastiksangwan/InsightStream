import { Suspense } from "react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { SavedContentPage } from "@/components/SavedContentPage";
import { getWatchLater } from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";

function WatchLaterFallback() {
  return (
    <main className="saved-page">
      <LoadingState message="Loading Watch Later..." />
    </main>
  );
}

async function WatchLaterContent() {
  try {
    const items = await getWatchLater(DEMO_USER_ID);

    return (
      <SavedContentPage
        title="Watch Later"
        subtitle="Titles saved for future viewing."
        badgeText="Personal watchlist"
        items={items}
        emptyTitle="No titles in Watch Later yet"
        emptyMessage="Open a content detail page and add something to Watch Later."
      />
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load Watch Later content from the backend.";

    return (
      <main className="saved-page">
        <section className="saved-hero">
          <span className="eyebrow">Personal watchlist</span>
          <h1>Watch Later</h1>
          <p>Titles saved for future viewing.</p>
        </section>

        <ErrorState
          title="Could not load Watch Later"
          message={`${message} Make sure the FastAPI backend is running at the configured API URL.`}
        />
      </main>
    );
  }
}

export default function WatchLaterPage() {
  return (
    <Suspense fallback={<WatchLaterFallback />}>
      <WatchLaterContent />
    </Suspense>
  );
}
