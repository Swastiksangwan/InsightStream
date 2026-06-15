"use client";

import { useState } from "react";

type PersonCreditCardProps = {
  name: string;
  subtitle: string;
  profileUrl?: string | null;
  variant?: "standard" | "compact";
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

export function PersonCreditCard({
  name,
  subtitle,
  profileUrl,
  variant = "standard",
}: PersonCreditCardProps) {
  const [showImage, setShowImage] = useState(Boolean(profileUrl));

  return (
    <article className={`person-credit-card person-credit-card--${variant}`}>
      <div className="person-credit-card__avatar" aria-hidden="true">
        {showImage && profileUrl ? (
          <img src={profileUrl} alt="" onError={() => setShowImage(false)} />
        ) : (
          <span>{getInitials(name)}</span>
        )}
      </div>

      <h3>{name}</h3>
      <p>{subtitle}</p>
    </article>
  );
}
