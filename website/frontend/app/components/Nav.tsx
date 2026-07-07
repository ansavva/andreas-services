import { Link, NavLink } from "react-router";

import { NAV_LINKS, SITE } from "~/lib/site";
import { ThemeToggle } from "./ThemeToggle";

export function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/85 backdrop-blur">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link to="/" className="font-heading text-lg font-semibold text-primary">
          {SITE.name}
        </Link>
        <div className="flex items-center gap-6 text-sm">
          <div className="hidden gap-6 sm:flex">
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
            className="rounded-md bg-primary px-4 py-2 font-medium text-primary-text transition-colors hover:bg-primary-hover"
          >
            Get a quote
          </Link>
        </div>
      </nav>
    </header>
  );
}
