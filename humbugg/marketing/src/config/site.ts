export const CANONICAL_ORIGIN = (import.meta.env.VITE_APP_BASE_URL || 'https://www.humbugg.com').replace(/\/$/, '');

// The product app is a separate deployment on its own origin, so every link to
// it is absolute and cross-origin — never a react-router <Link>.
export const APP_ORIGIN = (import.meta.env.VITE_APP_ORIGIN || 'https://app.humbugg.com').replace(/\/$/, '');

export function canonicalUrl(path = '/') {
  return new URL(path, `${CANONICAL_ORIGIN}/`).href;
}

export function appUrl(path = '/') {
  return new URL(path, `${APP_ORIGIN}/`).href;
}

/**
 * Maps a path this site used to serve onto its equivalent on the product app.
 * The auth and join paths carry over one-to-one; the old `/app` prefix is the
 * app's root, so `/app/settings` becomes `/settings`.
 */
export function legacyAppPath(pathname: string) {
  if (pathname === '/app') return '/';
  if (pathname.startsWith('/app/')) return pathname.slice('/app'.length);
  return pathname;
}
