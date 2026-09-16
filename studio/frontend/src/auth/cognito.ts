/**
 * The user pool's own JSON API, shared by the two files that call it.
 *
 * Plain `fetch`, like `oauth.ts`: the Cognito Identity Provider API is a JSON
 * POST with an `X-Amz-Target` header, and nothing studio calls on it needs
 * SigV4 — `account.ts` sends an access token as the credential, `signup.ts`
 * sends the public client id and nothing else. The API Gateway never sees
 * these; studio's own API has no route for them and needs none.
 */

const POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID as string | undefined;

/** `us-east-1_AbCdEf` → `https://cognito-idp.us-east-1.amazonaws.com/`. */
export function endpoint(): string {
  const region = POOL_ID?.split("_")[0];
  if (!region) {
    throw new Error(
      "Cognito is not configured. Run studio/scripts/dev-setup.sh; see studio/dev.env.sample.",
    );
  }
  return `https://cognito-idp.${region}.amazonaws.com/`;
}

/** Cognito's error body: a `__type` and a `message`, both optional in practice. */
export interface CognitoError {
  __type?: string;
  message?: string;
}

/**
 * What the failure means to the person, not what Cognito called it. The ones
 * that need translating: the scope — a session from before the client granted
 * `aws.cognito.signin.user.admin` fails with a message about the token, and
 * the fix is a sign-in, which nothing in that message says — and the sign-up
 * gate, whose refusal Cognito prefixes with the trigger's name and the words
 * "failed with error", which are for a developer and not for the person.
 */
export function describe(status: number, err: CognitoError): string {
  const type = err.__type?.split("#").pop() ?? "";
  const message = err.message ?? "";
  if (type === "NotAuthorizedException" && /scope/i.test(message)) {
    return "This session is too old to change the address. Sign out, sign back in, and try again.";
  }
  if (type === "UserLambdaValidationException") {
    const marker = "failed with error ";
    const at = message.indexOf(marker);
    return at >= 0 ? message.slice(at + marker.length).trim() : message;
  }
  if (type === "UsernameExistsException")
    return "An account with that address already exists. Sign in instead.";
  if (type === "InvalidPasswordException")
    return "That password does not meet the policy: at least 12 characters, with an uppercase letter, a lowercase letter and a digit.";
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

/** One operation against the pool. The caller supplies the whole body. */
export async function post<T>(target: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(endpoint(), {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}`,
    },
    body: JSON.stringify(body),
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
