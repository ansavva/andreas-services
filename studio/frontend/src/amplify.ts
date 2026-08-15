// Amplify's web wiring. Ported from `humbugg/app/src/amplify.ts` with the whole
// React Native polyfill block dropped: `crypto.getRandomValues`, `URL` and
// `localStorage` all exist in a browser, so Amplify's own defaults are correct
// here and adding an AsyncStorage shim would only be a layer.
import { Amplify } from "aws-amplify";

const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID ?? "";
const userPoolClientId = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";

export const AWS_REGION = import.meta.env.VITE_AWS_REGION ?? "us-east-1";

/**
 * Whether a user pool was configured at build time. False in a bare checkout
 * with no `.env.local`, and the auth context uses it to settle into "signed
 * out" rather than hanging on a session fetch that can only throw.
 */
export const isAuthConfigured = Boolean(userPoolId && userPoolClientId);

if (isAuthConfigured) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId,
        loginWith: { email: true },
      },
    },
  });
}
