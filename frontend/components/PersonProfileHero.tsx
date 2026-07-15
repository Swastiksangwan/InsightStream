"use client";

import { useState } from "react";
import type { PersonDetail } from "@/types/people";

type PersonProfileHeroProps = {
  person: PersonDetail;
};

function getInitials(name: string) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return initials || "IS";
}

function formatBirthday(value?: string | null) {
  if (!value) {
    return null;
  }

  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return value;
  }

  const [, year, month, day] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function PersonProfileHero({ person }: PersonProfileHeroProps) {
  const [showImage, setShowImage] = useState(Boolean(person.profile_url));
  const facts = [
    person.known_for_department
      ? { label: "Known for", value: person.known_for_department }
      : null,
    person.birthday ? { label: "Born", value: formatBirthday(person.birthday) } : null,
    person.place_of_birth
      ? { label: "Birthplace", value: person.place_of_birth }
      : null,
  ].filter((fact): fact is { label: string; value: string } => Boolean(fact?.value));

  return (
    <div className="person-hero__profile">
      <div className="person-profile-avatar" aria-label={`${person.name} profile image`}>
        {showImage && person.profile_url ? (
          <img
            src={person.profile_url}
            alt={`${person.name} profile`}
            onError={() => setShowImage(false)}
          />
        ) : (
          <span>{getInitials(person.name)}</span>
        )}
      </div>

      <div className="person-hero__copy">
        <h1>{person.name}</h1>
        {facts.length > 0 ? (
          <dl className="person-facts" aria-label="Person facts">
            {facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </div>
  );
}
