import { buttonClass } from '@ansavva/design-system';
import { Link } from 'react-router';
import type { HTMLAttributes, ReactNode } from 'react';

import { LEGAL_LINKS, SERVICE_COUNTRY, SERVICE_CURRENCY } from '../config/policies';
import { appUrl } from '../config/site';
import { ThemeToggle } from './ThemeToggle';

export function Brand() {
  return (
    <Link to="/" className="group flex items-center" aria-label="Humbugg home">
      <span className="brand-wordmark">Humbugg</span>
    </Link>
  );
}

export function Shell({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return (
    <div className="min-h-screen bg-bg text-ink">
      <header className="relative z-40 border-b border-line/80 bg-bg/95 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-5 lg:px-8">
          <Brand />
          {/* The product lives on another origin, so these are plain anchors —
              a react-router <Link> would try to resolve them as marketing routes. */}
          <nav className="flex items-center gap-2" aria-label="Primary navigation">
            {/* Pricing IS a marketing route, so it is the one nav item that is a <Link>.
                Never `hidden sm:` — it shipped that way for an hour and the pricing page was
                unreachable from a phone entirely, because the footer carries only policy links. */}
            {/* First in the row, so the three text actions read as one run and
                the icon sits apart from them. Still `hidden` below `sm` — unlike
                Pricing's link, this one DOES have another path: the footer
                mirrors it (below), so hiding the header copy on a narrow screen
                doesn't repeat the trap the Pricing comment describes. */}
            <ThemeToggle className="hidden sm:inline-flex" />
            <Link className="nav-link inline-flex" to="/pricing">Pricing</Link>
            <a className="nav-link hidden sm:inline-flex" href={appUrl('/login')}>Sign in</a>
            <a className={buttonClass()} href={appUrl('/login')}>Start a group</a>
          </nav>
        </div>
      </header>
      <main className={compact ? '' : 'mx-auto max-w-7xl px-5 py-10 lg:px-8'}>{children}</main>
      <SiteFooter />
    </div>
  );
}

export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-line/80 bg-bg">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-10 lg:px-8">
        <nav aria-label="Site" className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <Link to="/pricing" className="text-sm font-medium text-muted hover:text-ink hover:underline">
            Pricing
          </Link>
          {/* The header hides its copy of this control below `sm` — see the
              comment on it in `Shell` — so this is that control's only path on
              a narrow screen, the same reasoning "Sign in" never gets to use.
              Both instances share one preference (`useThemePreference` in
              `theme.ts`), so this one is never stale even though it mounts
              independently. */}
          <ThemeToggle className="sm:hidden" />
        </nav>
        <nav aria-label="Policies" className="flex flex-wrap gap-x-6 gap-y-3">
          {LEGAL_LINKS.map((link) => (
            <Link key={link.to} to={link.to} className="text-sm font-medium text-muted hover:text-ink hover:underline">
              {link.label}
            </Link>
          ))}
        </nav>
        <p className="text-sm text-muted">
          © {year} Humbugg · Available in the {SERVICE_COUNTRY} · Prices in {SERVICE_CURRENCY}
        </p>
      </div>
    </footer>
  );
}

export function StatusMessage({ message, tone = 'error' }: { message?: string | null; tone?: 'error' | 'success' }) {
  if (!message) return null;
  return <div role="status" className={`status-message ${tone === 'success' ? 'status-success' : 'status-error'}`}>{message}</div>;
}

export function Card({ children, className = '', ...props }: HTMLAttributes<HTMLElement> & { children: ReactNode }) {
  return <section className={`rounded-lg border border-line bg-card p-6 shadow-sm ${className}`} {...props}>{children}</section>;
}
