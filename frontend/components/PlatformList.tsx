import Link from "next/link";
import type { PlatformAvailability } from "@/types/content";

type PlatformListProps = {
  platforms: PlatformAvailability[];
};

const availabilityLabels: Record<string, string> = {
  streaming: "Streaming",
  rent: "Rent",
  buy: "Buy",
  ads: "Ads",
  free: "Free",
};

const regionLabels: Record<string, string> = {
  IN: "India",
  US: "US",
};

function normalizeDiscoverAvailabilityType(availabilityType?: string | null) {
  const normalized = availabilityType?.trim().toLowerCase();

  if (normalized === "stream") {
    return "streaming";
  }

  if (normalized === "streaming" || normalized === "rent" || normalized === "buy") {
    return normalized;
  }

  return null;
}

function buildDiscoverHref(platform: PlatformAvailability) {
  const params = [`platform=${encodeURIComponent(platform.name)}`];

  const availabilityType = normalizeDiscoverAvailabilityType(
    platform.availability_type,
  );

  if (availabilityType) {
    params.push(`availability_type=${encodeURIComponent(availabilityType)}`);
  }

  return `/discover?${params.join("&")}`;
}

function groupPlatforms(platforms: PlatformAvailability[]) {
  return platforms.reduce<Record<string, PlatformAvailability[]>>((groups, platform) => {
    const key = platform.availability_type || "available";
    groups[key] = groups[key] || [];
    groups[key].push(platform);
    return groups;
  }, {});
}

function availabilityRegionLabel(platforms: PlatformAvailability[]) {
  const regions = Array.from(
    new Set(
      platforms
        .map((platform) => platform.region_code)
        .filter((region): region is string => Boolean(region))
    )
  );

  if (regions.length === 0) {
    return null;
  }

  if (regions.length === 1) {
    const region = regions[0];
    return `Availability in ${regionLabels[region] || region}`;
  }

  return `Availability by region: ${regions.join(", ")}`;
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
  const regionLabel = availabilityRegionLabel(platforms);

  return (
    <section className="detail-panel">
      <div className="detail-panel__header">
        <span className="section-label">Where to watch</span>
        <h2>Availability</h2>
        {regionLabel ? <p className="availability-region">{regionLabel}</p> : null}
      </div>

      <div className="availability-groups">
        {Object.entries(groupedPlatforms).map(([type, items]) => (
          <div className="availability-group" key={type}>
            <h3>{availabilityLabels[type] || type}</h3>
            <div className="availability-list">
              {items.map((platform) => (
                <Link
                  className="availability-link"
                  href={buildDiscoverHref(platform)}
                  key={`${platform.name}-${platform.availability_type}-${platform.region_code || "legacy"}`}
                >
                  {platform.name}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
