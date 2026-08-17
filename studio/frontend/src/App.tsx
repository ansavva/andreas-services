import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Alert, Spinner } from "@ansavva/design-system";

import { isAuthConfigured } from "./amplify";
import { LoginForm } from "./components/auth/LoginForm";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrowsePage } from "./pages/BrowsePage";

function Gate() {
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

  return authenticated ? <BrowsePage /> : <LoginForm />;
}

/**
 * One route, matching everything.
 *
 * The path *is* the S3 key — `/projects/fred/runs/…/output/clip.mp4` — so there is
 * nothing to enumerate here and no depth to declare: a bucket's shape is not
 * known to the router. `BrowsePage` reads `location.pathname` through
 * `utils/location` and decides what it points at; a path that resolves to
 * nothing sensible falls back to the library root rather than 404ing, because a
 * stale bookmark should land somewhere usable.
 *
 * Two things outside this file have to agree with it. CloudFront's
 * viewer-request function must send these paths to `index.html` — including the
 * ones ending in `.mp4`, which is why it routes by location rather than by
 * extension (`infra/modules/hosting`). And sign-out sends the user to `/`, which
 * is the root listing.
 */
export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Gate />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
