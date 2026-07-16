export const CANONICAL_ORIGIN = (import.meta.env.VITE_APP_BASE_URL || 'https://humbugg.com').replace(/\/$/, '');

export function canonicalUrl(path = '/') {
  return new URL(path, `${CANONICAL_ORIGIN}/`).href;
}
