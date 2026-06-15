import type { PlatformAvailability } from "@/types/content";

type PlatformListProps = {
  platforms: PlatformAvailability[];
};

const availabilityLabels: Record<string, string> = {
  streaming: "Streaming",
  rent: "Rent",
  buy: "Buy",
};

function groupPlatforms(platforms: PlatformAvailability[]) {
  return platforms.reduce<Record<string, PlatformAvailability[]>>((groups, platform) => {
    const key = platform.availability_type || "available";
    groups[key] = groups[key] || [];
    groups[key].push(platform);
    return groups;
  }, {});
}

export function PlatformList({ platforms }: PlatformListProps) {
  if (platforms.length === 0) {
    return (
      <section className="detail-panel">
        <div className="detail-panel__header">
          <span className="section-label">Where to watch</span>
          <h2>Availability</h2>
        </div>
        <p className="detail-empty">No platform availability is listed yet.</p>
      </section>
    );
  }

  const groupedPlatforms = groupPlatforms(platforms);

  return (
    <section className="detail-panel">
      <div className="detail-panel__header">
        <span className="section-label">Where to watch</span>
        <h2>Availability</h2>
      </div>

      <div className="availability-groups">
        {Object.entries(groupedPlatforms).map(([type, items]) => (
          <div className="availability-group" key={type}>
            <h3>{availabilityLabels[type] || type}</h3>
            <div className="availability-list">
              {items.map((platform) => (
                <span key={`${platform.name}-${platform.availability_type}`}>
                  {platform.name}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
