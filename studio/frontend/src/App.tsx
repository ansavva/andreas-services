import type { ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Alert, Spinner } from "@ansavva/design-system";

import { isAuthConfigured } from "./amplify";
import { LoginForm } from "./components/auth/LoginForm";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrowsePage } from "./pages/BrowsePage";
import { LegacyRedirect } from "./pages/LegacyRedirect";

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
 * Three routes, and the third is a bridge.
 *
 * `/f/<node_id>` and `/o/<node_id>` are canonical (#313): the URL names a node
 * by id, so a share link outlives the rename or move that used to invalidate it.
 * `/` is the library root, whose id nothing knows before the first request.
 *
 * `*` is every URL studio handed out before that — the S3 key, spelled
 * `/projects/<project>/runs/…/output/clip.mp4` — and it goes to `LegacyRedirect`,
 * which asks the API what the path names and replaces itself with the id URL.
 * Matching those by *exclusion* is what reserves `/f/` and `/o/`; see
 * `utils/location`.
 *
 * **The gate wraps the routes rather than sitting inside one**, because the
 * resolver is an authenticated call: every `/api` route is behind the Cognito
 * authorizer, so a resolver rendered before sign-in would 401 on a link that is
 * perfectly good. Signing in leaves the URL where it was, and the redirect then
 * happens on the far side.
 *
 * Two things outside this file have to agree with it. CloudFront's
 * viewer-request function must send all of these to `index.html` — including the
 * legacy ones ending in `.mp4`, which is why it routes by location rather than
 * by extension (`infra/modules/hosting`). And sign-out sends the user to `/`.
 */
export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Gate>
          <Routes>
            <Route path="/" element={<BrowsePage />} />
            <Route path="/f/:nodeId" element={<BrowsePage />} />
            <Route path="/o/:nodeId" element={<BrowsePage />} />
            <Route path="*" element={<LegacyRedirect />} />
          </Routes>
        </Gate>
      </BrowserRouter>
    </AuthProvider>
  );
}
