"use client";

import Link from "next/link";
import { useState } from "react";

type PersonCreditCardProps = {
  name: string;
  subtitle: string;
  profileUrl?: string | null;
  href?: string;
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
  href,
  variant = "standard",
}: PersonCreditCardProps) {
  const [showImage, setShowImage] = useState(Boolean(profileUrl));
  const className = `person-credit-card person-credit-card--${variant}${
    href ? " person-credit-card--link" : ""
  }`;
  const content = (
    <>
      <div className="person-credit-card__avatar" aria-hidden="true">
        {showImage && profileUrl ? (
          <img src={profileUrl} alt="" onError={() => setShowImage(false)} />
        ) : (
          <span>{getInitials(name)}</span>
        )}
      </div>

      <h3>{name}</h3>
      <p>{subtitle}</p>
    </>
  );

  if (href) {
    return (
      <Link className={className} href={href} aria-label={`View ${name}`}>
        {content}
      </Link>
    );
  }

  return (
    <article className={className}>
      {content}
    </article>
  );
}
