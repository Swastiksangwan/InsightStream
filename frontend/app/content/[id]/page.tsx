import { CreditsSection } from "@/components/CreditsSection";
import { DetailHero } from "@/components/DetailHero";
import { DetailOverview } from "@/components/DetailOverview";
import { DetailSidebar } from "@/components/DetailSidebar";
import { ErrorState } from "@/components/ErrorState";
import { SeriesTimingCallout } from "@/components/SeriesTimingCallout";
import { SummaryPanel } from "@/components/SummaryPanel";
import {
  getContentCredits,
  getContentDetails,
  getWatched,
  getWatchLater,
} from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";
import type { Content, WatchStatus } from "@/types/content";
import type { ContentCreditsResponse } from "@/types/credits";

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

function emptyCredits(contentId: number): ContentCreditsResponse {
  return {
    content_id: contentId,
    cast: [],
    directors: [],
    creators: [],
    crew: [],
  };
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
      ? "Could not load watch status."
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
    const [initialWatchStateResult, creditsResult] = await Promise.allSettled([
      getInitialWatchState(details.content.id),
      getContentCredits(details.content.id),
    ]);

    const initialWatchState =
      initialWatchStateResult.status === "fulfilled"
        ? initialWatchStateResult.value
        : {
            status: "none" as WatchStatus,
            message: "Could not load watch status.",
          };

    const credits =
      creditsResult.status === "fulfilled"
        ? creditsResult.value
        : emptyCredits(details.content.id);

    return (
      <main className="detail-page-shell">
        <DetailHero
          content={details.content}
          credits={credits}
          seriesMetadata={details.series_metadata}
        />

        <section className="detail-content-grid" aria-label="Content detail sections">
          <div className="detail-main-column detail-main-column--overview">
            <SeriesTimingCallout
              contentType={details.content.type}
              seriesMetadata={details.series_metadata}
            />
            <DetailOverview content={details.content} genres={details.genres} />
          </div>

          <DetailSidebar
            contentId={details.content.id}
            initialStatus={initialWatchState.status}
            initialMessage={initialWatchState.message}
            platforms={details.platforms}
            ratings={details.ratings}
            seriesMetadata={details.series_metadata}
          />

          <div className="detail-main-column detail-main-column--supporting">
            <CreditsSection credits={credits} />
            <SummaryPanel summary={details.insight_summary} />
          </div>
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
