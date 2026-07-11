import { HomeContentCard } from "@/components/HomeContentCard";
import type { HomeContentCard as HomeContentCardType } from "@/types/content";

type HomePosterRailProps = {
  items: HomeContentCardType[];
};

export function HomePosterRail({ items }: HomePosterRailProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="home-poster-rail">
      {items.map((item) => (
        <HomeContentCard key={item.id} item={item} />
      ))}
    </div>
  );
}
