/**
 * Changing the signed-in address — two calls against the user pool itself.
 *
 * Two operations on the pool's own API (`cognito.ts`), with the access token
 * as the credential — no signing, and the API Gateway never sees them.
 *
 * The address is the username (`username_attributes = ["email"]` in
 * `infra/modules/auth`), so this changes what the person signs in with — on
 * the hosted page and in `studio login` alike. The pool is configured to keep
 * the old address in force until the new one is verified:
 *
 *   1. `requestEmailChange` → `UpdateUserAttributes` sends a code to the NEW
 *      address and changes nothing yet.
 *   2. `confirmEmailChange` → `VerifyUserAttribute` with the code performs the
 *      swap, then refreshes the tokens so the ID token's `email` claim — and
 *      the account menu that reads it — say the new address.
 *
 * A typo in step 1 therefore costs a code that never arrives, not the account.
 */
import { post } from "./cognito";
import { getAccessToken, refreshTokens } from "./oauth";

/** One self-service operation, with the session's access token as the credential. */
async function call<T>(target: string, body: Record<string, unknown>): Promise<T> {
  const accessToken = getAccessToken();
  if (!accessToken) throw new Error("Not signed in.");
  return post<T>(target, { AccessToken: accessToken, ...body });
}

interface UpdateUserAttributesResponse {
  CodeDeliveryDetailsList?: { Destination?: string }[];
}

/**
 * Step 1. Sends a verification code to `email` and returns the masked
 * destination Cognito reports (`a***@e***.com`), for the screen to echo.
 */
export async function requestEmailChange(email: string): Promise<string> {
  const res = await call<UpdateUserAttributesResponse>("UpdateUserAttributes", {
    UserAttributes: [{ Name: "email", Value: email }],
  });
  return res.CodeDeliveryDetailsList?.[0]?.Destination ?? email;
}

/**
 * Step 2. Verifies the code, which is the moment the address changes, then
 * renews the tokens so the ID token — and everything that reads it — carries
 * the new one. A session that cannot refresh is over (`refreshTokens` clears
 * it), and the next sign-in is with the new address.
 */
export async function confirmEmailChange(code: string): Promise<void> {
  await call<Record<string, never>>("VerifyUserAttribute", {
    AttributeName: "email",
    Code: code.trim(),
  });
  await refreshTokens();
}
