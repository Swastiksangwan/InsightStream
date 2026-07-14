"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useState } from "react";
import type { Content } from "@/types/content";

type ContentCardProps = {
  content: Content;
};

function formatType(type: Content["type"]) {
  return type === "movie" ? "Movie" : "Series";
}

function getFallbackText(title: string) {
  const initials = title
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return initials || "IS";
}

export function ContentCard({ content }: ContentCardProps) {
  const [showPoster, setShowPoster] = useState(Boolean(content.poster));
  const metaItems = [content.year, formatType(content.type)].filter(Boolean);
  const isLongTitle = content.title.length > 22;
  const titleSlideDistance = isLongTitle
    ? Math.min(190, Math.max(34, content.title.length * 7 - 160))
    : 0;
  const titleStyle = isLongTitle
    ? ({
        "--home-title-slide-distance": `-${titleSlideDistance}px`,
      } as CSSProperties)
    : undefined;

  return (
    <Link
      className="content-card"
      href={`/content/${content.id}`}
      aria-label={`View details for ${content.title}`}
    >
      <div className="content-card__poster">
        <div className="content-card__fallback" aria-hidden={showPoster}>
          <span className="content-card__fallback-mark">{getFallbackText(content.title)}</span>
        </div>

        {showPoster && content.poster ? (
          <img
            src={content.poster}
            alt={`${content.title} poster`}
            onError={() => setShowPoster(false)}
          />
        ) : null}

        {content.unified_score !== null && content.unified_score !== undefined ? (
          <div className="content-card__badges" aria-label="Content highlights">
            <span className="content-card__score">
              {Math.round(content.unified_score)}
            </span>
          </div>
        ) : null}
      </div>

      <div className="content-card__body">
        <h3 title={content.title}>
          <span
            className={isLongTitle ? "home-title-marquee" : undefined}
            style={titleStyle}
          >
            {content.title}
          </span>
        </h3>
        {metaItems.length > 0 ? (
          <div className="content-card__meta" aria-label="Content metadata">
            {metaItems.map((item) => (
              <span key={String(item)}>{item}</span>
            ))}
          </div>
        ) : null}
      </div>
    </Link>
  );
}
