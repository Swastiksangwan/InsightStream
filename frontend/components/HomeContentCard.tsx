"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useState } from "react";
import type { HomeContentCard as HomeContentCardType } from "@/types/content";

type HomeContentCardProps = {
  item: HomeContentCardType;
};

function formatContentType(contentType: HomeContentCardType["content_type"]) {
  return contentType === "series" ? "Series" : "Movie";
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

export function HomeContentCard({ item }: HomeContentCardProps) {
  const [showPoster, setShowPoster] = useState(Boolean(item.poster_url));
  const meta = [item.year, formatContentType(item.content_type)].filter(Boolean);
  const isLongTitle = item.title.length > 22;
  const titleSlideDistance = isLongTitle
    ? Math.min(190, Math.max(34, item.title.length * 7 - 160))
    : 0;
  const titleStyle = isLongTitle
    ? ({
        "--home-title-slide-distance": `-${titleSlideDistance}px`,
      } as CSSProperties)
    : undefined;

  return (
    <Link
      className="home-card"
      href={`/content/${item.id}`}
      aria-label={`View details for ${item.title}`}
    >
      <div className="home-card__poster">
        <div className="home-card__fallback" aria-hidden={showPoster}>
          <span>{getFallbackText(item.title)}</span>
        </div>

        {showPoster && item.poster_url ? (
          <img
            src={item.poster_url}
            alt={`${item.title} poster`}
            onError={() => setShowPoster(false)}
          />
        ) : null}

        <div className="home-card__badges" aria-label="Content highlights">
          {item.unified_score !== null && item.unified_score !== undefined ? (
            <span className="home-card__score">{Math.round(item.unified_score)}</span>
          ) : null}
        </div>
      </div>

      <div className="home-card__body">
        <h3 title={item.title}>
          <span
            className={isLongTitle ? "home-title-marquee" : undefined}
            style={titleStyle}
          >
            {item.title}
          </span>
        </h3>
        {meta.length > 0 ? (
          <div className="home-card__meta">
            {meta.map((value) => (
              <span key={String(value)}>{value}</span>
            ))}
          </div>
        ) : null}
      </div>
    </Link>
  );
}
