import { useEffect, type ReactNode } from "react";
import { BrowserRouter, useLocation } from "react-router-dom";

import { Alert, Spinner } from "@ansavva/design-system";

import { CALLBACK_PATH, login } from "./auth/oauth";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { LibraryProvider, useLibrary } from "./context/LibraryContext";
import { StudioRoutes } from "./routes";

/**
 * Signed in, or on the way to Cognito's hosted sign-in page.
 *
 * **There is no in-app form to render any more.** A signed-out visitor is sent
 * to Managed Login, which owns the password, the forced first change, the
 * reset and the TOTP challenge — all four of which the deleted
 * `components/auth/LoginForm.tsx` either faked or could not do. So the
 * signed-out branch is a redirect and a spinner, not a screen.
 *
 * The redirect is in an effect rather than in the render path because it is a
 * navigation: building the authorize URL hashes a PKCE verifier, which is
 * async, and starting that during render would fire it on every re-render.
 */
function Gate({ children }: { children: ReactNode }) {
  const { authenticated, loading, configured } = useAuth();
  const { pathname, search } = useLocation();

  useEffect(() => {
    if (!configured || loading || authenticated) return;
    // Where they were headed, so the hosted round trip lands them back on it
    // rather than on home. The module-level `login`, not the context's: the
    // context value is rebuilt on every auth state change, and depending on it
    // here would re-fire the redirect.
    void login(`${pathname}${search}`);
  }, [authenticated, configured, loading, pathname, search]);

  if (!configured) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="max-w-md">
          <Alert.Root intent="warning">
            <Alert.Title>Auth is not configured</Alert.Title>
            <Alert.Description>
              Set VITE_COGNITO_CLIENT_ID and VITE_COGNITO_DOMAIN (see .env.local.example).
            </Alert.Description>
          </Alert.Root>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Spinner size="lg" label={loading ? "Restoring your session" : "Taking you to sign in"} />
      </div>
    );
  }

  return <>{children}</>;
}

/**
 * The gate, and everything behind it.
 *
 * Split out of `App` so `/auth/callback` can skip it: that route completes
 * sign-in, so it necessarily renders with no session, and the gate would bounce
 * it back to the hosted page in a loop. It cannot simply live inside the gate
 * either — `LibraryProvider` below fetches on mount, and there is no token to
 * fetch with until the exchange this bypass exists for has finished.
 */
function GatedApp() {
  const { pathname } = useLocation();

  if (pathname === CALLBACK_PATH) return <StudioRoutes />;

  return (
    <Gate>
      {/* Inside the gate: the library list is an authenticated call, and there
          is no token to make it with before sign-in. */}
      <LibraryProvider>
        <LibraryGate />
      </LibraryProvider>
    </Gate>
  );
}

/**
 * Nothing renders until the library list has landed.
 *
 * Every listing route is scoped to a library, and a caller in more than one gets
 * a 400 telling them to name one — so a page rendered before `GET /api/libraries`
 * answers would fire exactly the requests that cannot succeed yet, and the
 * spinner would be replaced by an error that fixes itself a moment later.
 *
 * **A caller in *no* library is a real state and says so.** The pool is
 * admin-create-only, so it means an account somebody created and never added to
 * a library — a provisioning gap, and the fix is `scripts/add-member.sh`. The
 * API answers this route with an empty list rather than a 403 precisely so it can
 * be diagnosed; showing "loading" forever would throw that away.
 *
 * `key` on the routes is what makes switching library discard every cached
 * listing: they live in component state throughout the tree, and remounting is
 * the one thing that is certain to drop all of them. See `LibrarySwitcher`.
 */
function LibraryGate() {
  const { current, loading, error } = useLibrary();

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Spinner size="lg" label="Opening your library" />
      </div>
    );
  }

  if (error || current === null) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="max-w-md">
          <Alert.Root intent={error ? "danger" : "warning"}>
            <Alert.Title>{error ? "Could not load your libraries" : "No library yet"}</Alert.Title>
            <Alert.Description>
              {error ?? "Your account is not a member of any library. Ask for access."}
            </Alert.Description>
          </Alert.Root>
        </div>
      </div>
    );
  }

  // **`key` on the route table and not on a wrapping element.** `Routes`
  // renders no DOM of its own, so remounting it discards every hook's state
  // without putting a `<div>` between `#root` and the page — which would break
  // the `min-h-full` chain the layout hangs off.
  // **Inside the library gate, around the routes.** A page that throws should
  // leave the shell and the library it was in intact — and remounting on a
  // library switch resets the boundary with everything else, so an error from
  // one library does not survive into another.
  return (
    <ErrorBoundary key={current}>
      <StudioRoutes />
    </ErrorBoundary>
  );
}

/**
 * The gate wraps the routes rather than sitting inside one.
 *
 * Every screen behind it makes an authenticated call on mount — every `/api`
 * route is behind the Cognito authorizer — so a page rendered before sign-in
 * would 401 on a link that is perfectly good. The URL is stashed before the
 * hosted round trip and restored after it, so the screen a link named renders
 * on the far side of signing in.
 *
 * The route table itself is in `routes.tsx`. See there for what each shape means.
 */
export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <GatedApp />
      </BrowserRouter>
    </AuthProvider>
  );
}
