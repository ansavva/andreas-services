import { useState } from "react";

import { Alert, Button, Field, Input, Text } from "@ansavva/design-system";

import { login } from "../auth/oauth";
import { confirmSignUp, resendCode, signUp } from "../auth/signup";

/** The sign-up page's address. Outside the auth gate, like the callback. */
export const SIGNUP_PATH = "/signup";

/**
 * Create an account. The second screen in studio that renders with no session.
 *
 * **This page exists because Managed Login's own sign-up page cannot pass the
 * gate.** The pool refuses any sign-up that does not carry the invite code in
 * `ClientMetadata`, and the hosted page has no field for it — so a person who
 * follows the hosted page's "Create an account" link is refused with a message
 * naming this path. Sign-in itself stays on the hosted page: this collects the
 * address, the password and the code, confirms the account, and then hands over
 * to the same authorize leg every other visit takes.
 *
 * The library comes after sign-in, not here: `POST /api/libraries` needs a
 * token, and `LibraryGate` in `App.tsx` offers it the moment a signed-in
 * account is found to be in no library.
 */
export function SignUpPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = email.trim();
  const looksLikeAddress = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed);
  const canRegister = looksLikeAddress && password.length >= 12 && invite.trim() !== "";

  async function register() {
    if (!canRegister || busy) return;
    setBusy(true);
    setError(null);
    try {
      setSentTo(await signUp(trimmed, password, invite.trim()));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!code.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await confirmSignUp(trimmed, code);
      setConfirmed(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await resendCode(trimmed);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <div className="flex w-full max-w-md flex-col gap-4">
        <Text variant="heading">Create an account</Text>

        {confirmed ? (
          <>
            <Text variant="body" tone="muted">
              Your account is ready. Sign in to make your first library.
            </Text>
            <Button onClick={() => void login("/")}>Sign in</Button>
          </>
        ) : sentTo === null ? (
          <>
            <Text variant="body" tone="muted">
              Studio is invite-only. You need a code from whoever runs it.
            </Text>
            <Field.Root name="email" invalid={trimmed !== "" && !looksLikeAddress}>
              <Field.Label>Email</Field.Label>
              <Input
                type="email"
                autoComplete="email"
                value={email}
                onValueChange={setEmail}
                placeholder="you@example.com"
                autoFocus
              />
            </Field.Root>
            <Field.Root name="password" invalid={password !== "" && password.length < 12}>
              <Field.Label>Password</Field.Label>
              <Input
                type="password"
                autoComplete="new-password"
                value={password}
                onValueChange={setPassword}
              />
              <Field.Description>
                At least 12 characters, with an uppercase letter, a lowercase letter and a digit.
              </Field.Description>
            </Field.Root>
            <Field.Root name="invite">
              <Field.Label>Invite code</Field.Label>
              <Input
                type="password"
                autoComplete="off"
                value={invite}
                onValueChange={setInvite}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void register();
                }}
              />
            </Field.Root>
          </>
        ) : (
          <>
            <Text variant="body" tone="muted">
              A code was sent to <span className="font-mono">{sentTo}</span>. Enter it to
              confirm the account.
            </Text>
            <Field.Root name="code">
              <Field.Label>Confirmation code</Field.Label>
              <Input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onValueChange={setCode}
                placeholder="Six digits"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") void confirm();
                }}
              />
            </Field.Root>
          </>
        )}

        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not create the account</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}

        {!confirmed && (
          <div className="flex flex-wrap items-center justify-end gap-2">
            {sentTo === null ? (
              <>
                <Button intent="secondary" onClick={() => void login("/")}>
                  I have an account
                </Button>
                <Button disabled={!canRegister || busy} onClick={() => void register()}>
                  {busy ? "Creating…" : "Create account"}
                </Button>
              </>
            ) : (
              <>
                <Button intent="secondary" disabled={busy} onClick={() => void resend()}>
                  Send a new code
                </Button>
                <Button disabled={!code.trim() || busy} onClick={() => void confirm()}>
                  {busy ? "Confirming…" : "Confirm"}
                </Button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
