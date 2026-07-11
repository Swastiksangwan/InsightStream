"use client";

import { useMemo, useState } from "react";
import { HomePosterRail } from "@/components/HomePosterRail";
import type { HomeBucket } from "@/types/content";

type HomeBucketSectionProps = {
  buckets: HomeBucket[];
};

export function HomeBucketSection({ buckets }: HomeBucketSectionProps) {
  const nonEmptyBuckets = useMemo(
    () => buckets.filter((bucket) => bucket.items.length > 0),
    [buckets],
  );
  const [activeBucketId, setActiveBucketId] = useState(
    nonEmptyBuckets[0]?.bucket_id ?? "",
  );

  if (nonEmptyBuckets.length === 0) {
    return null;
  }

  const activeBucket =
    nonEmptyBuckets.find((bucket) => bucket.bucket_id === activeBucketId) ??
    nonEmptyBuckets[0];

  return (
    <div className="home-bucket-panel">
      <div className="home-bucket-tabs" role="tablist" aria-label="Homepage buckets">
        {nonEmptyBuckets.map((bucket) => (
          <button
            key={bucket.bucket_id}
            type="button"
            role="tab"
            aria-selected={bucket.bucket_id === activeBucket.bucket_id}
            className="home-bucket-tab"
            onClick={() => setActiveBucketId(bucket.bucket_id)}
          >
            {bucket.label}
          </button>
        ))}
      </div>

      <div className="home-bucket-panel__copy">
        <h3>{activeBucket.label}</h3>
        <p>{activeBucket.subtitle}</p>
      </div>

      <HomePosterRail items={activeBucket.items} />
    </div>
  );
}
