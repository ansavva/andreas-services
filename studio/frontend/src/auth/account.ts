/**
 * Changing the signed-in address — two calls against the user pool itself.
 *
 * Plain `fetch`, like `oauth.ts`: the Cognito Identity Provider API is a JSON
 * POST with an `X-Amz-Target` header, and the two operations here need no
 * signing because the access token is the credential. The API Gateway never
 * sees these; studio's own API has no route for them and needs none.
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
import { getAccessToken, refreshTokens } from "./oauth";

const POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID as string | undefined;

/** `us-east-1_AbCdEf` → `https://cognito-idp.us-east-1.amazonaws.com/`. */
function endpoint(): string {
  const region = POOL_ID?.split("_")[0];
  if (!region) {
    throw new Error(
      "Cognito is not configured. Run studio/scripts/dev-setup.sh; see studio/dev.env.sample.",
    );
  }
  return `https://cognito-idp.${region}.amazonaws.com/`;
}

/** Cognito's error body: a `__type` and a `message`, both optional in practice. */
interface CognitoError {
  __type?: string;
  message?: string;
}

/**
 * What the failure means to the person, not what Cognito called it. The one
 * that needs translating is the scope: a session from before the client
 * granted `aws.cognito.signin.user.admin` fails here with a message about the
 * token, and the fix is a sign-in, which nothing in that message says.
 */
function describe(status: number, err: CognitoError): string {
  const type = err.__type?.split("#").pop() ?? "";
  const message = err.message ?? "";
  if (type === "NotAuthorizedException" && /scope/i.test(message)) {
    return "This session is too old to change the address. Sign out, sign back in, and try again.";
  }
  if (type === "CodeMismatchException") return "That code is not right.";
  if (type === "ExpiredCodeException")
    return "That code has expired. Start again to get a new one.";
  if (type === "AliasExistsException")
    return "Another account already uses that address.";
  if (type === "InvalidParameterException")
    return message || "That address is not valid.";
  if (type === "LimitExceededException")
    return "Too many attempts. Wait a while, then try again.";
  return message || `Cognito returned HTTP ${status}.`;
}

async function call<T>(
  target: string,
  body: Record<string, unknown>,
): Promise<T> {
  const accessToken = getAccessToken();
  if (!accessToken) throw new Error("Not signed in.");

  const response = await fetch(endpoint(), {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}`,
    },
    body: JSON.stringify({ AccessToken: accessToken, ...body }),
  });

  if (!response.ok) {
    let err: CognitoError = {};
    try {
      err = (await response.json()) as CognitoError;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(describe(response.status, err));
  }
  return (await response.json()) as T;
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
