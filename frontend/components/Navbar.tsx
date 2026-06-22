"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/discover", label: "Discover" },
  { href: "/watch-later", label: "Watch Later" },
  { href: "/watched", label: "Watched" },
];

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");

  function isActiveRoute(href: string) {
    if (href === "/") {
      return pathname === href;
    }

    return pathname.startsWith(href);
  }

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const query = searchQuery.trim();

    if (!query) {
      return;
    }

    router.push(`/search?q=${encodeURIComponent(query)}`);
  }

  return (
    <header className="navbar">
      <div className="navbar__inner">
        <Link className="navbar__brand" href="/" aria-label="InsightStream home">
          <span className="navbar__mark" aria-hidden="true" />
          <span>InsightStream</span>
        </Link>

        <nav className="navbar__links" aria-label="Primary navigation">
          {navItems.map((item) => {
            const isActive = isActiveRoute(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <form
          className="navbar-search"
          role="search"
          onSubmit={handleSearchSubmit}
        >
          <input
            aria-label="Search local catalog"
            type="search"
            placeholder="Search catalog"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
          />
          <button type="submit">Search</button>
        </form>
      </div>
    </header>
  );
}
