import { DetailHero } from "@/components/DetailHero";
import { ErrorState } from "@/components/ErrorState";
import { PlatformList } from "@/components/PlatformList";
import { RatingList } from "@/components/RatingList";
import { SummaryPanel } from "@/components/SummaryPanel";
import { getContentDetails } from "@/lib/api";

type ContentDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

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

    return (
      <main className="detail-page-shell">
        <DetailHero content={details.content} genres={details.genres} />

        <section className="detail-layout" aria-label="Decision support details">
          <SummaryPanel summary={details.summary} />
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
