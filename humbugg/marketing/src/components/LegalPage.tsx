import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router';

import { Shell } from './Layout';
import {
  LEGAL_LINKS,
  POLICY_VERSION,
  SUPPORT_EMAIL,
  policyEffectiveDateLabel,
} from '../config/policies';

export function LegalPage({
  title,
  summary,
  children,
}: {
  title: string;
  summary: string;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  return (
    <Shell>
      <article className="mx-auto max-w-3xl py-6">
        <header>
          <p className="eyebrow">Humbugg policies</p>
          <h1 className="mt-3 font-heading text-4xl font-semibold leading-tight sm:text-5xl">{title}</h1>
          <p className="mt-4 text-lg leading-8 text-muted">{summary}</p>
          <p className="mt-4 text-sm text-muted">
            Version {POLICY_VERSION} · Effective {policyEffectiveDateLabel()}
          </p>
        </header>
        <nav aria-label="Policies" className="mt-6 flex flex-wrap gap-x-5 gap-y-2 border-y border-line py-4 text-sm">
          {LEGAL_LINKS.map((link) =>
            link.to === pathname ? (
              <span key={link.to} aria-current="page" className="font-semibold text-ink">
                {link.label}
              </span>
            ) : (
              <Link key={link.to} to={link.to} className="font-medium text-accent hover:underline">
                {link.label}
              </Link>
            ),
          )}
        </nav>
        <div className="legal-prose mt-8">{children}</div>
        <footer className="mt-12 border-t border-line pt-6 text-sm text-muted">
          <p>
            Questions about these policies? Contact{' '}
            <a className="text-accent hover:underline" href={`mailto:${SUPPORT_EMAIL}`}>
              {SUPPORT_EMAIL}
            </a>
            .
          </p>
        </footer>
      </article>
    </Shell>
  );
}
