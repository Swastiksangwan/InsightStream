import { DetailHero } from "@/components/DetailHero";
import { ErrorState } from "@/components/ErrorState";
import { PlatformList } from "@/components/PlatformList";
import { RatingList } from "@/components/RatingList";
import { SummaryPanel } from "@/components/SummaryPanel";
import { WatchActionButtons } from "@/components/WatchActionButtons";
import { getContentDetails, getWatched, getWatchLater } from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";
import type { Content, WatchStatus } from "@/types/content";

type ContentDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

type InitialWatchState = {
  status: WatchStatus;
  message?: string;
};

function includesContent(items: Content[], contentId: number) {
  return items.some((item) => item.id === contentId);
}

async function getInitialWatchState(contentId: number): Promise<InitialWatchState> {
  const [watchLaterResult, watchedResult] = await Promise.allSettled([
    getWatchLater(DEMO_USER_ID),
    getWatched(DEMO_USER_ID),
  ]);

  const watchLaterItems =
    watchLaterResult.status === "fulfilled" ? watchLaterResult.value : [];
  const watchedItems = watchedResult.status === "fulfilled" ? watchedResult.value : [];

  const message =
    watchLaterResult.status === "rejected" || watchedResult.status === "rejected"
      ? "Could not load current watch status for the demo user."
      : undefined;

  if (includesContent(watchedItems, contentId)) {
    return { status: "watched", message };
  }

  if (includesContent(watchLaterItems, contentId)) {
    return { status: "watch_later", message };
  }

  return { status: "none", message };
}

export default async function ContentDetailPage({ params }: ContentDetailPageProps) {
  const { id } = await params;
  const contentId = Number(id);

  if (!Number.isInteger(contentId) || contentId <= 0) {
    return (
      <main className="detail-page-shell">
        <ErrorState
          title="Invalid content"
          message="This content page could not be loaded because the content ID is invalid."
        />
      </main>
    );
  }

  try {
    const details = await getContentDetails(contentId);
    const initialWatchState = await getInitialWatchState(details.content.id);

    return (
      <main className="detail-page-shell">
        <DetailHero content={details.content} genres={details.genres} />

        <section className="detail-layout" aria-label="Decision support details">
          <SummaryPanel summary={details.summary} />
          <WatchActionButtons
            contentId={details.content.id}
            title={details.content.title}
            initialStatus={initialWatchState.status}
            initialMessage={initialWatchState.message}
          />
          <PlatformList platforms={details.platforms} />
          <RatingList ratings={details.ratings} />
        </section>
      </main>
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load this content detail page.";

    return (
      <main className="detail-page-shell">
        <ErrorState
          title="Could not load content details"
          message={`${message} Make sure the FastAPI backend is running and the content exists.`}
        />
      </main>
    );
  }
}
