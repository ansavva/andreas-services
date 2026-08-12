// Where the *other* half of Humbugg lives.
//
// Splitting the SSR app in two means the legal pages, the marketing home and the
// post-deletion landing page are no longer routes this app can reach — they are
// another origin. Every link to them is therefore absolute, and the origin is
// build-time configuration so a PR preview or a local dev server can point
// somewhere else.
import { LEGAL_LINKS, type LegalLink } from './policies';

/** The marketing site's origin. Production is `https://www.humbugg.com`. */
export const WEB_BASE_URL = (process.env.EXPO_PUBLIC_WEB_BASE_URL ?? 'https://www.humbugg.com').replace(/\/$/, '');

/** Turns a marketing-site path (`/terms`) into an absolute URL. */
export function webUrl(path: string): string {
  return `${WEB_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

export interface ExternalLink {
  href: string;
  label: string;
}

/**
 * `LEGAL_LINKS` from `config/policies` is shared verbatim with the marketing
 * site, where the paths are local routes. Here they have to cross an origin, so
 * they are resolved once rather than at every call site.
 */
export const LEGAL_EXTERNAL_LINKS: readonly ExternalLink[] = LEGAL_LINKS.map((link: LegalLink) => ({
  href: webUrl(link.to),
  label: link.label,
}));
