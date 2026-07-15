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
  const paragraphs =
    biography
      ?.trim()
      .split(/\n{2,}/)
      .map((paragraph) => paragraph.trim())
      .filter(Boolean) || [];

  if (!hasBiography) {
    return <p className="detail-empty">Biography not available yet.</p>;
  }

  return (
    <div className="person-biography__body">
      <div
        className={
          shouldToggle && !expanded ? "person-biography__copy--clamped" : undefined
        }
      >
        {paragraphs.map((paragraph, index) => (
          <p key={`${index}-${paragraph.slice(0, 24)}`}>{paragraph}</p>
        ))}
      </div>

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
