import { Suspense } from "react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { SavedContentPage } from "@/components/SavedContentPage";
import { getWatched } from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";

function WatchedFallback() {
  return (
    <main className="saved-page">
      <LoadingState message="Loading Watched titles..." />
    </main>
  );
}

async function WatchedContent() {
  try {
    const items = await getWatched(DEMO_USER_ID);

    return (
      <SavedContentPage
        title="Watched"
        subtitle="Titles you have marked as watched."
        badgeText="Personal history"
        items={items}
        emptyTitle="No watched titles yet"
        emptyMessage="Open a content detail page and mark something as watched."
      />
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load Watched content from the backend.";

    return (
      <main className="saved-page">
        <section className="saved-hero">
          <span className="eyebrow">Personal history</span>
          <h1>Watched</h1>
          <p>Titles you have marked as watched.</p>
        </section>

        <ErrorState
          title="Could not load Watched"
          message={`${message} Make sure the FastAPI backend is running at the configured API URL.`}
        />
      </main>
    );
  }
}

export default function WatchedPage() {
  return (
    <Suspense fallback={<WatchedFallback />}>
      <WatchedContent />
    </Suspense>
  );
}
