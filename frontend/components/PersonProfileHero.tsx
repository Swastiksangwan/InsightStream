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

export function PersonProfileHero({ person }: PersonProfileHeroProps) {
  const [showImage, setShowImage] = useState(Boolean(person.profile_url));

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
        <span className="eyebrow">Person Profile</span>
        <h1>{person.name}</h1>
        {person.known_for_department ? (
          <div className="person-metadata" aria-label="Person metadata">
            <span>{person.known_for_department}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
