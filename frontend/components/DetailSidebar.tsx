import { PlatformList } from "@/components/PlatformList";
import { RatingList } from "@/components/RatingList";
import { SeriesInfoPanel } from "@/components/SeriesInfoPanel";
import { WatchActionButtons } from "@/components/WatchActionButtons";
import type {
  PlatformAvailability,
  Rating,
  SeriesMetadata,
  WatchStatus,
} from "@/types/content";

type DetailSidebarProps = {
  contentId: number;
  initialStatus: WatchStatus;
  initialMessage?: string;
  platforms: PlatformAvailability[];
  ratings: Rating[];
  seriesMetadata?: SeriesMetadata | null;
};

export function DetailSidebar({
  contentId,
  initialStatus,
  initialMessage,
  platforms,
  ratings,
  seriesMetadata,
}: DetailSidebarProps) {
  return (
    <aside className="detail-sidebar" aria-label="Personal and availability details">
      <WatchActionButtons
        contentId={contentId}
        initialStatus={initialStatus}
        initialMessage={initialMessage}
      />
      <SeriesInfoPanel seriesMetadata={seriesMetadata} />
      <PlatformList platforms={platforms} />
      <RatingList ratings={ratings} />
    </aside>
  );
}
