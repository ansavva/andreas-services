export const CANONICAL_ORIGIN = (import.meta.env.VITE_APP_BASE_URL || 'https://www.humbugg.com').replace(/\/$/, '');

// The product app is a separate deployment on its own origin, so every link to
// it is absolute and cross-origin — never a react-router <Link>.
export const APP_ORIGIN = (import.meta.env.VITE_APP_ORIGIN || 'https://app.humbugg.com').replace(/\/$/, '');

/**
 * The API's origin.
 *
 * Same shape as `APP_ORIGIN` above, and same reason: the API is a separate deployment on its own
 * host, so every call to it is absolute and cross-origin. The default is the production host, which
 * is why adding the pricing page needed no deploy-time variable — only local development overrides
 * it, through `VITE_API_BASE_URL` in `.env.local`.
 */
export const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL || 'https://api.humbugg.com').replace(/\/$/, '');

export function apiUrl(path = '/') {
  return new URL(path, `${API_ORIGIN}/`).href;
}

export function canonicalUrl(path = '/') {
  return new URL(path, `${CANONICAL_ORIGIN}/`).href;
}

export function appUrl(path = '/') {
  return new URL(path, `${APP_ORIGIN}/`).href;
}
