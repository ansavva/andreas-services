/**
 * Server-only runtime configuration. These are read from the Lambda's
 * environment (set by Terraform + the deploy workflow). Never import this from
 * client code — it is `.server` so React Router strips it from the browser
 * bundle.
 */
export const env = {
  /** Absolute base URL of the Python backend API, including the `/api` suffix,
   *  e.g. `https://website-api.andreas.services/api`. */
  apiBase: process.env.WEBSITE_API_URL ?? "",
  /** Cognito pool/client for admin login + token verification. */
  cognitoUserPoolId: process.env.COGNITO_USER_POOL_ID ?? "",
  cognitoClientId: process.env.COGNITO_CLIENT_ID ?? "",
  /** Host serving the hosted sign-in pages, e.g. `website-auth.andreas.services`. */
  cognitoDomain: process.env.COGNITO_DOMAIN ?? "",
  /** Client secret — the code exchange is confidential and runs only here. */
  cognitoClientSecret: process.env.COGNITO_CLIENT_SECRET ?? "",
  /** Public origin of the site. CloudFront strips Host before the SSR Lambda,
   *  so `request.url` carries the Function URL — unusable as an OAuth redirect
   *  URI, which Cognito matches character for character. Unset locally, where
   *  the dev server is the origin. */
  publicOrigin: process.env.PUBLIC_ORIGIN ?? "http://localhost:5173",
  /** Secret used to sign the admin session cookie. */
  sessionSecret: process.env.SESSION_SECRET ?? "dev-insecure-session-secret",
};

export function requireApiBase(): string {
  if (!env.apiBase) {
    throw new Error("WEBSITE_API_URL is not configured");
  }
  return env.apiBase;
}
