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
  /** Secret used to sign the admin session cookie. */
  sessionSecret: process.env.SESSION_SECRET ?? "dev-insecure-session-secret",
  region: process.env.AWS_REGION ?? process.env.AWS_DEFAULT_REGION ?? "us-east-1",
};

export function requireApiBase(): string {
  if (!env.apiBase) {
    throw new Error("WEBSITE_API_URL is not configured");
  }
  return env.apiBase;
}
