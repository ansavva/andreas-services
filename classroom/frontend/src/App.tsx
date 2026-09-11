import { Suspense, lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Spinner } from "@ansavva/design-system";

import { Header } from "./components/Header";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./context/AuthContext";
import { CALLBACK_PATH } from "./auth/oauth";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { PagesListPage } from "./pages/PagesListPage";

/**
 * Split out because it carries JSZip.
 *
 * The original reason was stronger and is gone: this app used to serve students
 * too, at `/p/:slug`, and lazy-loading kept a class off a phone from
 * downloading a rich-text editor. Students now open their lesson's own files on
 * a different host entirely and never load this bundle at all.
 *
 * What is left is modest but real — the unzipping library is only needed on the
 * screen that uploads a lesson, and the list screen is what a teacher opens
 * first.
 */
const PageEditorPage = lazy(() =>
  import("./pages/PageEditorPage").then((m) => ({ default: m.PageEditorPage })),
);

function EditorLoading() {
  return (
    <div className="flex justify-center p-12">
      <Spinner />
    </div>
  );
}

/**
 * ONE audience now: the teacher.
 *
 * `/p/:slug` used to render a page for students here. It is gone — students
 * open their lesson's own files on a different host entirely
 * (`classroom.andreas.services`), served straight from S3 by CloudFront. This
 * app is the admin surface and every route in it requires a session.
 */
export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path={CALLBACK_PATH} element={<AuthCallbackPage />} />
          <Route
            path="*"
            element={
              <>
                <Header />
                <Routes>
                  <Route
                    path="/"
                    element={
                      <ProtectedRoute>
                        <PagesListPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/pages/new"
                    element={
                      <ProtectedRoute>
                        <Suspense fallback={<EditorLoading />}>
                          <PageEditorPage />
                        </Suspense>
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/pages/:pageId"
                    element={
                      <ProtectedRoute>
                        <Suspense fallback={<EditorLoading />}>
                          <PageEditorPage />
                        </Suspense>
                      </ProtectedRoute>
                    }
                  />
                </Routes>
              </>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
