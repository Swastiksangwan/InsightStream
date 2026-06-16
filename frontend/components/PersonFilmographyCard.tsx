"use client";

import Link from "next/link";
import { useState } from "react";
import type { PersonCreditItem } from "@/types/people";

type PersonFilmographyCardProps = {
  item: PersonCreditItem;
  roleLabel: string;
};

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

function formatType(contentType: PersonCreditItem["content_type"]) {
  return contentType === "movie"
    ? "Movie"
    : contentType === "series"
      ? "Series"
      : contentType;
}

export function PersonFilmographyCard({
  item,
  roleLabel,
}: PersonFilmographyCardProps) {
  const [showPoster, setShowPoster] = useState(Boolean(item.poster_url));
  const metaItems = [item.year, formatType(item.content_type)].filter(Boolean);

  return (
    <Link
      className="person-filmography-card"
      href={`/content/${item.content_id}`}
      aria-label={`View ${item.title}`}
    >
      <div className="person-filmography-card__poster">
        <div className="person-filmography-card__fallback" aria-hidden={showPoster}>
          <span>{getFallbackText(item.title)}</span>
        </div>

        {showPoster && item.poster_url ? (
          <img
            src={item.poster_url}
            alt={`${item.title} poster`}
            onError={() => setShowPoster(false)}
          />
        ) : null}
      </div>

      <div className="person-filmography-card__body">
        <div className="person-filmography-card__meta">
          {metaItems.map((meta) => (
            <span key={String(meta)}>{meta}</span>
          ))}
        </div>
        <h3>{item.title}</h3>
        <p>{roleLabel}</p>
      </div>
    </Link>
  );
}
