import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Header } from "./components/Header";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./context/AuthContext";
import { CALLBACK_PATH } from "./auth/oauth";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { PageEditorPage } from "./pages/PageEditorPage";
import { PagesListPage } from "./pages/PagesListPage";
import { PublicPageView } from "./pages/PublicPageView";

/**
 * Two audiences, one bundle.
 *
 * `/p/:slug` is the student's reader and is deliberately outside
 * `ProtectedRoute` — a student following a link has no account. Everything else
 * is the teacher's own workspace and requires a session.
 */
export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/p/:slug" element={<PublicPageView />} />
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
                        <PageEditorPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/pages/:pageId"
                    element={
                      <ProtectedRoute>
                        <PageEditorPage />
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
