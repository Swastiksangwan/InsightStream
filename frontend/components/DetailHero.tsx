"use client";

import Link from "next/link";
import { useState } from "react";
import type { Content } from "@/types/content";
import type { ContentCreditsResponse, CreditCrewMember } from "@/types/credits";

type DetailHeroProps = {
  content: Content;
  credits?: ContentCreditsResponse | null;
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

function formatPeopleList(people: CreditCrewMember[]) {
  return people.map((person) => person.name).join(", ");
}

export function DetailHero({ content, credits }: DetailHeroProps) {
  const [showBackdrop, setShowBackdrop] = useState(Boolean(content.backdrop));
  const [showPoster, setShowPoster] = useState(Boolean(content.poster));
  const primaryPeople =
    content.type === "movie" ? credits?.directors || [] : credits?.creators || [];
  const primaryPeopleLabel =
    content.type === "movie" ? "Directed by" : "Created by";
  const metadata = [
    formatType(content.type),
    content.year,
    formatRuntime(content.runtime),
    content.language,
    content.age_rating,
  ].filter(Boolean);

  return (
    <section className="detail-hero">
      {showBackdrop && content.backdrop ? (
        <img
          className="detail-hero__backdrop-image"
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

            {primaryPeople.length > 0 ? (
              <div className="detail-key-credit" aria-label={primaryPeopleLabel}>
                <span>{primaryPeopleLabel}</span>
                <strong>{formatPeopleList(primaryPeople)}</strong>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
