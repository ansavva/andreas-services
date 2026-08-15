import { useState, type FormEvent } from "react";

import { Alert, Button, Field, Input, Text } from "@ansavva/design-system";

import { useAuth } from "../../context/AuthContext";

type Mode = "signIn" | "newPassword" | "requestReset" | "confirmReset";

/**
 * The one unauthenticated screen.
 *
 * There is no sign-up path because the pool is admin-create-only — the flows
 * here are the three a user of such a pool can actually reach: signing in,
 * setting a password on a freshly created account, and resetting a forgotten
 * one.
 */
export function LoginForm() {
  const { login, completeNewPassword, beginReset, finishReset, newPasswordRequired } = useAuth();

  const [mode, setMode] = useState<Mode>("signIn");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const effectiveMode: Mode = newPasswordRequired ? "newPassword" : mode;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);

    try {
      if (effectiveMode === "signIn") {
        await login(email, password);
      } else if (effectiveMode === "newPassword") {
        await completeNewPassword(password);
      } else if (effectiveMode === "requestReset") {
        await beginReset(email);
        setNotice("Check your email for a reset code.");
        setMode("confirmReset");
      } else {
        await finishReset(email, code, password);
        setNotice("Password updated. Sign in with your new password.");
        setMode("signIn");
        setPassword("");
        setCode("");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <form
        onSubmit={submit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-lg border border-line bg-card p-6"
      >
        <div>
          <Text variant="display">Studio</Text>
          <Text variant="caption" tone="muted">
            {effectiveMode === "newPassword"
              ? "Choose a password for your account."
              : effectiveMode === "signIn"
                ? "Sign in to browse the media library."
                : "Reset your password."}
          </Text>
        </div>

        {error && (
          <Alert.Root intent="danger">
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}
        {notice && (
          <Alert.Root intent="info">
            <Alert.Description>{notice}</Alert.Description>
          </Alert.Root>
        )}

        {effectiveMode !== "newPassword" && (
          <Field.Root name="email">
            <Field.Label>Email</Field.Label>
            <Input type="email" value={email} onValueChange={setEmail} placeholder="you@example.com" />
          </Field.Root>
        )}

        {effectiveMode === "confirmReset" && (
          <Field.Root name="code">
            <Field.Label>Reset code</Field.Label>
            <Input value={code} onValueChange={setCode} placeholder="123456" />
          </Field.Root>
        )}

        {effectiveMode !== "requestReset" && (
          <Field.Root name="password">
            <Field.Label>
              {effectiveMode === "signIn" ? "Password" : "New password"}
            </Field.Label>
            <Input type="password" value={password} onValueChange={setPassword} />
          </Field.Root>
        )}

        <Button type="submit" disabled={busy}>
          {busy
            ? "Working…"
            : effectiveMode === "signIn"
              ? "Sign in"
              : effectiveMode === "newPassword"
                ? "Set password"
                : effectiveMode === "requestReset"
                  ? "Send reset code"
                  : "Update password"}
        </Button>

        {effectiveMode === "signIn" && (
          <Button type="button" intent="ghost" size="sm" onClick={() => setMode("requestReset")}>
            Forgot your password?
          </Button>
        )}
        {(effectiveMode === "requestReset" || effectiveMode === "confirmReset") && (
          <Button type="button" intent="ghost" size="sm" onClick={() => setMode("signIn")}>
            Back to sign in
          </Button>
        )}
      </form>
    </div>
  );
}
