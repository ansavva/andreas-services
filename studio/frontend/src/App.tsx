import { useEffect, useMemo, useState, type ReactNode } from "react";
import { BrowserRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";

import { Alert, Button, Field, Input, Text, Toast } from "@ansavva/design-system";

import { ApertureSpinner } from "./components/common/Aperture";
import { CALLBACK_PATH, login } from "./auth/oauth";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { LibraryProvider, useLibrary } from "./context/LibraryContext";
import { SIGNUP_PATH } from "./pages/SignUpPage";
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
              Set VITE_COGNITO_CLIENT_ID and VITE_COGNITO_DOMAIN in dev.env (see studio/dev.env.sample).
            </Alert.Description>
          </Alert.Root>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <ApertureSpinner size="lg" label={loading ? "Restoring your session" : "Taking you to sign in"} />
      </div>
    );
  }

  return <>{children}</>;
}

/**
 * An account in no library, and the one thing it can do about that.
 *
 * `create` puts the new library into the context and selects it, so the gate
 * above re-renders straight into the routes — no reload, no second fetch. A
 * failure stays on this screen with the reason; the account is unchanged.
 */
function FirstLibrary() {
  const { create } = useLibrary();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const trimmed = name.trim();

  async function submit() {
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await create(trimmed);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <div className="flex w-full max-w-md flex-col gap-4">
        <Text variant="heading">Name your library</Text>
        <Text variant="body" tone="muted">
          Everything you make lives in a library. This account is not in one yet, so
          start with an empty one — you can be added to others later.
        </Text>
        <Field.Root name="library">
          <Field.Label>Library name</Field.Label>
          <Input
            value={name}
            onValueChange={setName}
            placeholder="My library"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") void submit();
            }}
          />
        </Field.Root>
        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not create the library</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}
        <div className="flex justify-end">
          <Button disabled={!trimmed || busy} onClick={() => void submit()}>
            {busy ? "Creating…" : "Create library"}
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * The gate, and everything behind it.
 *
 * Split out of `App` so `/auth/callback` and `/signup` can skip it: the first
 * completes sign-in and the second precedes it, so both necessarily render
 * with no session, and the gate would bounce either back to the hosted page. It cannot simply live inside the gate
 * either — `LibraryProvider` below fetches on mount, and there is no token to
 * fetch with until the exchange this bypass exists for has finished.
 */
function GatedApp() {
  const { pathname } = useLocation();

  if (pathname === CALLBACK_PATH || pathname === SIGNUP_PATH) return <StudioRoutes />;

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
 * **A caller in *no* library is a real state, and the fix is offered here.**
 * It is a fresh account — one that just signed up, or one an administrator
 * created and never added to a library — and either way the next step is the
 * same: make one. `POST /api/libraries` is the one write an account in no
 * library can make, and `FirstLibrary` below is the form that makes it. The
 * API answers the listing with an empty list rather than a 403 precisely so
 * this screen can exist; showing "loading" forever would throw that away.
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
        <ApertureSpinner size="lg" label="Opening your library" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="max-w-md">
          <Alert.Root intent="danger">
            <Alert.Title>Could not load your libraries</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        </div>
      </div>
    );
  }

  if (current === null) return <FirstLibrary />;

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
 * would 401 on a link that is perfectly good. The URL is stashed before the
 * hosted round trip and restored after it, so the screen a link named renders
 * on the far side of signing in.
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
    // `GatedApp` rather than the gate inline: it has to read the location to
    // let `/auth/callback` through unauthenticated, and only a child of the
    // router can. The query client wraps everything, including that path —
    // clearing the cache on a library switch has to outlive any one route.
    // The toast store sits outside the router and the gates, so a message
    // queued by a write survives the navigation that follows it — deleting
    // the folder you are in steps up into its parent, and the toast is what
    // says the delete happened. Its viewport is a portal to `document.body`
    // and draws nothing until something is queued.
    <QueryClientProvider client={client}>
      <Toast.Provider>
        <AuthProvider>
          <BrowserRouter>
            <GatedApp />
          </BrowserRouter>
        </AuthProvider>
        <Toast.Viewport />
      </Toast.Provider>
    </QueryClientProvider>
  );
}

/**
 * Empty the cache when the library changes.
 *
 * **The remount above is not enough on its own, and that is what a cache
 * costs.** A cache outlives the components that filled it, so without this a
 * switch would redraw the previous library's characters from memory and only
 * correct itself when something refetched. Keys are not library-scoped instead, because that would
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
