import { Link, NavLink } from "react-router";

import { NAV_LINKS, SITE } from "~/lib/site";
import { ThemeToggle } from "./ThemeToggle";

export function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/85 backdrop-blur">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link to="/" className="min-w-0 font-heading text-lg font-semibold text-primary">
          <span className="hidden min-[390px]:inline">{SITE.name}</span>
          <span className="min-[390px]:hidden">AS</span>
        </Link>
        <div className="flex items-center gap-2 text-sm sm:gap-4">
          <div className="hidden gap-6 md:flex">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `transition-colors hover:text-primary ${isActive ? "text-primary" : "text-muted"}`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </div>
          <ThemeToggle />
          <Link
            to="/services"
            className="inline-flex h-9 items-center whitespace-nowrap rounded-md bg-primary px-3 text-sm font-medium text-primary-text transition-colors hover:bg-primary-hover sm:px-4"
          >
            <span className="hidden min-[360px]:inline">Get a quote</span>
            <span className="min-[360px]:hidden">Quote</span>
          </Link>
          <details className="relative md:hidden">
            <summary
              aria-label="Open navigation menu"
              className="grid h-9 w-9 cursor-pointer list-none place-items-center rounded-md text-muted transition-colors hover:bg-surface-alt hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg [&::-webkit-details-marker]:hidden"
            >
              <svg
                width="19"
                height="19"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                aria-hidden
              >
                <path d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </summary>
            <div className="absolute right-0 top-11 w-48 rounded-md border border-line bg-card p-2 shadow-lg">
              {NAV_LINKS.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) =>
                    `block rounded px-3 py-2 font-medium transition-colors hover:bg-surface-alt hover:text-primary ${
                      isActive ? "text-primary" : "text-ink"
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              ))}
            </div>
          </details>
        </div>
      </nav>
    </header>
  );
}
