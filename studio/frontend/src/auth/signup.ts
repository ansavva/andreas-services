/**
 * Creating an account — two unauthenticated calls against the user pool.
 *
 * The pool accepts self sign-up, gated: its pre-sign-up trigger refuses any
 * `SignUp` whose `ClientMetadata` does not carry the invite code
 * (`infra/modules/auth`, and the handler under
 * `backend/studio_core/handlers/aws/signup/`). The code is metadata, not an
 * attribute, so it reaches the trigger and is stored nowhere.
 *
 *   1. `signUp` → `SignUp` with the address, the password and the code. Cognito
 *      emails a confirmation code; the account exists but cannot sign in.
 *   2. `confirmSignUp` → `ConfirmSignUp` with that code. Now it can — through
 *      Managed Login like every other account, which is where the page sends
 *      the person next. The library comes after: `POST /api/libraries`, made
 *      by the gate in `App.tsx` once there is a token to make it with.
 *
 * `studio signup` in the CLI drives the same two calls and then the same route.
 */
import { post } from "./cognito";

const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;

/** The `ClientMetadata` key the trigger reads. Must match the handler's `INVITE_KEY`. */
export const INVITE_METADATA_KEY = "invite_code";

function clientId(): string {
  if (!CLIENT_ID) {
    throw new Error(
      "Cognito is not configured. Run studio/scripts/dev-setup.sh; see studio/dev.env.sample.",
    );
  }
  return CLIENT_ID;
}

interface SignUpResponse {
  CodeDeliveryDetails?: { Destination?: string };
}

/**
 * Step 1. Returns the masked destination Cognito reports (`a***@e***.com`),
 * for the screen to echo.
 */
export async function signUp(email: string, password: string, inviteCode: string): Promise<string> {
  const res = await post<SignUpResponse>("SignUp", {
    ClientId: clientId(),
    Username: email,
    Password: password,
    UserAttributes: [{ Name: "email", Value: email }],
    ClientMetadata: { [INVITE_METADATA_KEY]: inviteCode },
  });
  return res.CodeDeliveryDetails?.Destination ?? email;
}

/** Step 2. After this the account can sign in. */
export async function confirmSignUp(email: string, code: string): Promise<void> {
  await post<Record<string, never>>("ConfirmSignUp", {
    ClientId: clientId(),
    Username: email,
    ConfirmationCode: code.trim(),
  });
}

/** Another code, for one that expired or never arrived. */
export async function resendCode(email: string): Promise<void> {
  await post<Record<string, never>>("ResendConfirmationCode", {
    ClientId: clientId(),
    Username: email,
  });
}
