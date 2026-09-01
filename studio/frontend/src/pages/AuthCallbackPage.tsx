import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Alert, Button } from "@ansavva/design-system";

import { ApertureSpinner } from "../components/common/Aperture";
import { useAuth } from "../context/AuthContext";
import { handleCallback } from "../auth/oauth";

/**
 * Where Cognito sends the browser back with `?code=`.
 *
 * The one screen in studio that renders with no session — it is what creates
 * one. `App` therefore routes it outside the auth gate: the gate's job is to
 * bounce a signed-out visitor to the hosted page, and doing that here would be
 * an infinite loop through the very redirect that just completed.
 *
 * **The exchange must run once.** An authorization code is single-use, so a
 * second `POST /oauth2/token` with the same code fails — and under React
 * StrictMode every effect in development runs twice. The ref is what makes the
 * second run a no-op; a dependency array cannot, because the effect body is
 * what is being guarded, not what it depends on.
 */
export function AuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    handleCallback(params)
      .then((returnTo) => {
        // Before the navigation: the screen it lands on fetches on mount, and
        // those requests need the context to already know there is a token.
        refresh();
        // `replace`, so a back-press does not return to a spent code.
        navigate(returnTo, { replace: true });
      })
      .catch((err: Error) => setError(err.message));
  }, [navigate, params, refresh]);

  if (error) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="flex max-w-md flex-col gap-4">
          <Alert.Root intent="danger">
            <Alert.Title>Could not finish signing in</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
          {/* A full reload rather than a route change: the gate is what starts
              a fresh authorize leg, and it only runs on mount. */}
          <Button onClick={() => window.location.assign("/")}>Start again</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full items-center justify-center">
      <ApertureSpinner size="lg" label="Signing you in" />
    </div>
  );
}
