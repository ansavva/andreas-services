import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Spinner } from "@ansavva/design-system";

import { handleCallback } from "../auth/oauth";

/**
 * Completes the code exchange and forwards to wherever the user was headed.
 *
 * The exchange runs exactly once. React 18's StrictMode mounts effects twice in
 * development, and a second exchange would spend an authorization code Cognito
 * has already redeemed — which fails, and would show a sign-in error on a
 * sign-in that actually worked.
 */
export function AuthCallbackPage() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    handleCallback(new URLSearchParams(window.location.search))
      .then((returnTo) => navigate(returnTo, { replace: true }))
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Sign-in failed."),
      );
  }, [navigate]);

  if (error) {
    return (
      <div className="mx-auto max-w-md p-8">
        <Alert.Root intent="danger">
          <Alert.Title>Sign-in failed</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
        <div className="mt-4">
          <Button onClick={() => navigate("/", { replace: true })}>Start again</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner />
    </div>
  );
}
