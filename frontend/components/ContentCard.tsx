"use client";

import { useState } from "react";
import type { Content } from "@/types/content";

type ContentCardProps = {
  content: Content;
};

function formatRuntime(runtime?: number | null) {
  if (!runtime) {
    return null;
  }

  return `${runtime} min`;
}

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

function getShortTitle(title: string) {
  const words = title.split(/\s+/).filter(Boolean);

  if (words.length <= 3) {
    return title;
  }

  return `${words.slice(0, 3).join(" ")}...`;
}

export function ContentCard({ content }: ContentCardProps) {
  const [showPoster, setShowPoster] = useState(Boolean(content.poster));
  const runtime = formatRuntime(content.runtime);
  const metaItems = [
    content.year,
    formatType(content.type),
    runtime,
    content.age_rating,
  ].filter(Boolean);

  return (
    <article className="content-card">
      <div className="content-card__poster">
        <div className="content-card__fallback" aria-hidden={showPoster}>
          <span className="content-card__fallback-mark">
            {getFallbackText(content.title)}
          </span>
          <span className="content-card__fallback-title">
            {getShortTitle(content.title)}
          </span>
        </div>

        {showPoster && content.poster ? (
          <img
            src={content.poster}
            alt={`${content.title} poster`}
            onError={() => setShowPoster(false)}
          />
        ) : null}
      </div>

      <div className="content-card__body">
        <div className="content-card__meta" aria-label="Content metadata">
          {metaItems.map((item) => (
            <span key={String(item)}>{item}</span>
          ))}
        </div>

        <h3>{content.title}</h3>
        <p className="content-card__overview">
          {content.overview || "No overview is available yet."}
        </p>
      </div>
    </article>
  );
}
