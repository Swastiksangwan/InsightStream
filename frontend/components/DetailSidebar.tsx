import { PlatformList } from "@/components/PlatformList";
import { RatingList } from "@/components/RatingList";
import { WatchActionButtons } from "@/components/WatchActionButtons";
import type { PlatformAvailability, Rating, WatchStatus } from "@/types/content";

type DetailSidebarProps = {
  contentId: number;
  initialStatus: WatchStatus;
  initialMessage?: string;
  platforms: PlatformAvailability[];
  ratings: Rating[];
};

export function DetailSidebar({
  contentId,
  initialStatus,
  initialMessage,
  platforms,
  ratings,
}: DetailSidebarProps) {
  return (
    <aside className="detail-sidebar" aria-label="Personal and availability details">
      <WatchActionButtons
        contentId={contentId}
        initialStatus={initialStatus}
        initialMessage={initialMessage}
      />
      <PlatformList platforms={platforms} />
      <RatingList ratings={ratings} />
    </aside>
  );
}
