import { useEffect, useMemo, type ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";

import { Alert, Spinner } from "@ansavva/design-system";

import { isAuthConfigured } from "./amplify";
import { LoginForm } from "./components/auth/LoginForm";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
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
  // **Inside the library gate, around the routes.** A page that throws should
  // leave the shell and the library it was in intact — and remounting on a
  // library switch resets the boundary with everything else, so an error from
  // one library does not survive into another.
  return (
    <ErrorBoundary key={current}>
      <DiscardOnLibrarySwitch library={current} />
      <StudioRoutes />
    </ErrorBoundary>
  );
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
  /**
   * One client for the app's lifetime.
   *
   * `staleTime` is deliberately short rather than zero: it is long enough that
   * going back to a page you were just on is instant, and short enough that a
   * library somebody else is also writing to does not look frozen. Retries are
   * off because every call here is behind an authorizer that answers 401 the
   * same way three times, and a failed listing already offers its own retry.
   */
  const client = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: false, refetchOnWindowFocus: false },
        },
      }),
    [],
  );

  return (
    <QueryClientProvider client={client}>
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
    </QueryClientProvider>
  );
}

/**
 * Empty the cache when the library changes.
 *
 * **The remount above is no longer enough, and that is what a cache costs.**
 * Discarding component state used to discard every answer with it; a cache
 * outlives the components that filled it, so without this a switch would redraw
 * the previous library's characters from memory and only correct itself when
 * something refetched. Keys are not library-scoped instead, because that would
 * put the library context inside `useResource` and every component test would
 * need a provider to render at all.
 *
 * Renders nothing. It is an effect that needs to sit inside the provider.
 */
function DiscardOnLibrarySwitch({ library }: { library: string }) {
  const client = useQueryClient();
  useEffect(() => {
    client.clear();
  }, [client, library]);
  return null;
}
