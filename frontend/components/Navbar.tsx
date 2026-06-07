"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/discover", label: "Discover" },
  { href: "/watch-later", label: "Watch Later" },
  { href: "/watched", label: "Watched" },
];

export function Navbar() {
  const pathname = usePathname();

  function isActiveRoute(href: string) {
    if (href === "/") {
      return pathname === href;
    }

    return pathname.startsWith(href);
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

        <span className="navbar__status">API-powered MVP</span>
      </div>
    </header>
  );
}
