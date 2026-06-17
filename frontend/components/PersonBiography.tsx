"use client";

import { useState } from "react";

type PersonBiographyProps = {
  biography?: string | null;
};

const TOGGLE_THRESHOLD = 720;

export function PersonBiography({ biography }: PersonBiographyProps) {
  const [expanded, setExpanded] = useState(false);
  const hasBiography = Boolean(biography?.trim());
  const shouldToggle = hasBiography && (biography?.length || 0) > TOGGLE_THRESHOLD;

  if (!hasBiography) {
    return <p className="detail-empty">Biography not available yet.</p>;
  }

  return (
    <div className="person-biography__body">
      <p
        className={
          shouldToggle && !expanded ? "person-biography__copy--clamped" : undefined
        }
      >
        {biography}
      </p>

      {shouldToggle ? (
        <button
          className="person-biography__toggle"
          type="button"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "Show less" : "Read more"}
        </button>
      ) : null}
    </div>
  );
}
