import type { ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";

import { Alert, Spinner } from "@ansavva/design-system";

import { isAuthConfigured } from "./amplify";
import { LoginForm } from "./components/auth/LoginForm";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LibraryProvider, useLibrary } from "./context/LibraryContext";
import { StudioRoutes } from "./routes";

function Gate({ children }: { children: ReactNode }) {
  const { authenticated, loading } = useAuth();

  if (!isAuthConfigured) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="max-w-md">
          <Alert.Root intent="warning">
            <Alert.Title>Auth is not configured</Alert.Title>
            <Alert.Description>
              Set VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_CLIENT_ID (see .env.local.example).
            </Alert.Description>
          </Alert.Root>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Spinner size="lg" label="Restoring your session" />
      </div>
    );
  }

  return authenticated ? <>{children}</> : <LoginForm />;
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
  return <StudioRoutes key={current} />;
}

/**
 * The gate wraps the routes rather than sitting inside one.
 *
 * Every screen behind it makes an authenticated call on mount — every `/api`
 * route is behind the Cognito authorizer — so a page rendered before sign-in
 * would 401 on a link that is perfectly good. Signing in leaves the URL where it
 * was, and the screen it names renders on the far side of it.
 *
 * The route table itself is in `routes.tsx`. See there for what each shape means.
 */
export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Gate>
          {/* Inside the gate: the library list is an authenticated call, and
              there is no token to make it with before sign-in. */}
          <LibraryProvider>
            <LibraryGate />
          </LibraryProvider>
        </Gate>
      </BrowserRouter>
    </AuthProvider>
  );
}
