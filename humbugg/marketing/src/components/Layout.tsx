import { buttonClass } from '@ansavva/design-system';
import { Link } from 'react-router';
import type { HTMLAttributes, ReactNode } from 'react';

import { LEGAL_LINKS, SERVICE_COUNTRY, SERVICE_CURRENCY } from '../config/policies';
import { appUrl } from '../config/site';

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
            {/* Pricing IS a marketing route, so it is the one nav item that is a <Link>. */}
            <Link className="nav-link hidden sm:inline-flex" to="/pricing">Pricing</Link>
            <a className="nav-link hidden sm:inline-flex" href={appUrl('/login')}>Sign in</a>
            <a className={buttonClass()} href={appUrl('/signup')}>Start a group</a>
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
  return <section className={`rounded-2xl border border-line bg-card p-6 shadow-sm ${className}`} {...props}>{children}</section>;
}
