import type { ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";

import { Alert, Spinner } from "@ansavva/design-system";

import { isAuthConfigured } from "./amplify";
import { LoginForm } from "./components/auth/LoginForm";
import { AuthProvider, useAuth } from "./context/AuthContext";
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
 * The gate wraps the routes rather than sitting inside one.
 *
 * `LegacyRedirect` makes an authenticated call — every `/api` route is behind
 * the Cognito authorizer — so a resolver rendered before sign-in would 401 on a
 * share link that is perfectly good. Signing in leaves the URL where it was, and
 * the redirect happens on the far side of it.
 *
 * The route table itself is in `routes.tsx`. See there for what the three shapes
 * mean.
 */
export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Gate>
          <StudioRoutes />
        </Gate>
      </BrowserRouter>
    </AuthProvider>
  );
}
