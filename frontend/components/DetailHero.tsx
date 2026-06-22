"use client";

import Link from "next/link";
import { useState } from "react";
import type { Content, SeriesMetadata } from "@/types/content";
import type { ContentCreditsResponse, CreditCrewMember } from "@/types/credits";

type DetailHeroProps = {
  content: Content;
  credits?: ContentCreditsResponse | null;
  seriesMetadata?: SeriesMetadata | null;
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

function certificationLabel(content: Content) {
  if (!content.age_rating) {
    return null;
  }

  if (content.age_rating_region) {
    const system = content.age_rating_system || content.age_rating_region;
    return `${content.age_rating_region} certification${system ? ` (${system})` : ""}`;
  }

  return "Age rating";
}

function titleCaseStatus(status?: string | null) {
  if (!status) {
    return null;
  }

  return status
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function DetailHero({ content, credits, seriesMetadata }: DetailHeroProps) {
  const [showBackdrop, setShowBackdrop] = useState(Boolean(content.backdrop));
  const [showPoster, setShowPoster] = useState(Boolean(content.poster));
  const primaryPeople =
    content.type === "movie" ? credits?.directors || [] : credits?.creators || [];
  const primaryPeopleLabel =
    content.type === "movie" ? "Directed by" : "Created by";
  const seriesStatusLabel =
    content.type === "series"
      ? titleCaseStatus(seriesMetadata?.series_status_normalized) ||
        seriesMetadata?.series_status
      : null;
  const metadata = [
    { label: formatType(content.type), title: "Content type" },
    content.year ? { label: String(content.year), title: "Release year" } : null,
    formatRuntime(content.runtime)
      ? { label: formatRuntime(content.runtime) || "", title: "Runtime" }
      : null,
    content.language ? { label: content.language, title: "Language" } : null,
    content.age_rating
      ? {
          label: content.age_rating,
          title: certificationLabel(content) || "Age rating",
        }
      : null,
    seriesStatusLabel
      ? { label: seriesStatusLabel, title: "Series lifecycle status" }
      : null,
    content.type === "series" && seriesMetadata?.number_of_seasons
      ? {
          label: `${seriesMetadata.number_of_seasons} season${
            seriesMetadata.number_of_seasons === 1 ? "" : "s"
          }`,
          title: "Season count",
        }
      : null,
  ].filter((item): item is { label: string; title: string } => Boolean(item));

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
                <span key={item.label} title={item.title}>
                  {item.label}
                </span>
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
