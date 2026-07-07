import { Link } from "react-router";

import { NAV_LINKS, SITE, SOCIALS } from "~/lib/site";
import { SOCIAL_ICONS } from "./SocialIcons";

/** Footer doubles as the sitemap + link hub (every path + every social). */
export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="mt-24 border-t border-line bg-surface-alt/40">
      <div className="mx-auto grid max-w-6xl gap-10 px-6 py-14 sm:grid-cols-3">
        <div>
          <p className="font-heading text-lg font-semibold text-primary">{SITE.name}</p>
          <p className="mt-2 max-w-xs text-sm text-muted">{SITE.tagline}</p>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Site</p>
          <ul className="mt-3 space-y-2 text-sm">
            <li>
              <Link to="/" className="text-ink transition-colors hover:text-primary">
                Home
              </Link>
            </li>
            {NAV_LINKS.map((link) => (
              <li key={link.to}>
                <Link to={link.to} className="text-ink transition-colors hover:text-primary">
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Elsewhere</p>
          <div className="mt-3 flex gap-2">
            {SOCIALS.map((social) => (
              <a
                key={social.label}
                href={social.href}
                aria-label={social.label}
                title={social.label}
                target="_blank"
                rel="noreferrer"
                className="grid h-9 w-9 place-items-center rounded-md border border-line text-muted transition-colors hover:border-primary hover:bg-primary hover:text-primary-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
              >
                {SOCIAL_ICONS[social.label]}
              </a>
            ))}
          </div>
        </div>
      </div>
      <div className="border-t border-line/70">
        <p className="mx-auto max-w-6xl px-6 py-6 text-xs text-muted">
          © {year} {SITE.name}. Built with AI, in public.
        </p>
      </div>
    </footer>
  );
}
