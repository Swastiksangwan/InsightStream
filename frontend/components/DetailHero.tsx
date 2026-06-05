"use client";

import Link from "next/link";
import { useState } from "react";
import type { Content } from "@/types/content";

type DetailHeroProps = {
  content: Content;
  genres: string[];
};

function formatType(type: Content["type"]) {
  return type === "movie" ? "Movie" : "Series";
}

function formatRuntime(runtime?: number | null) {
  return runtime ? `${runtime} min` : null;
}

function getInitials(title: string) {
  const initials = title
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return initials || "IS";
}

export function DetailHero({ content, genres }: DetailHeroProps) {
  const [showBackdrop, setShowBackdrop] = useState(Boolean(content.backdrop));
  const [showPoster, setShowPoster] = useState(Boolean(content.poster));
  const metadata = [
    formatType(content.type),
    content.year,
    formatRuntime(content.runtime),
    content.language,
    content.age_rating,
  ].filter(Boolean);

  return (
    <section
      className="detail-hero"
      style={
        showBackdrop && content.backdrop
          ? { backgroundImage: `url(${content.backdrop})` }
          : undefined
      }
    >
      {showBackdrop && content.backdrop ? (
        <img
          className="detail-hero__backdrop-probe"
          src={content.backdrop}
          alt=""
          aria-hidden="true"
          onError={() => setShowBackdrop(false)}
        />
      ) : null}

      <div className="detail-hero__overlay">
        <Link className="detail-back-link" href="/">
          Back to homepage
        </Link>

        <div className="detail-hero__grid">
          <div className="detail-poster" aria-label={`${content.title} poster`}>
            <div className="detail-poster__fallback" aria-hidden={showPoster}>
              <span>{getInitials(content.title)}</span>
              <small>InsightStream</small>
            </div>

            {showPoster && content.poster ? (
              <img
                src={content.poster}
                alt={`${content.title} poster`}
                onError={() => setShowPoster(false)}
              />
            ) : null}
          </div>

          <div className="detail-hero__content">
            <div className="eyebrow">Content details</div>
            <h1>{content.title}</h1>

            <div className="detail-metadata" aria-label="Content metadata">
              {metadata.map((item) => (
                <span key={String(item)}>{item}</span>
              ))}
            </div>

            {genres.length > 0 ? (
              <div className="genre-chip-list" aria-label="Genres">
                {genres.map((genre) => (
                  <span key={genre}>{genre}</span>
                ))}
              </div>
            ) : null}

            <p>{content.overview || "No overview is available yet."}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
