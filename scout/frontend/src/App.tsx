import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@/context/ThemeContext";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { RegionRedirect } from "@/pages/RegionRedirect";
import { EventsListPage } from "@/pages/EventsListPage";
import { EventDetailPage } from "@/pages/EventDetailPage";
import { AdminPage } from "@/pages/AdminPage";
import "@/index.css";

// Strip trailing slash so React Router's basename is well-formed (e.g. "/app" not "/app/")
const basename = ((import.meta.env.VITE_BASE as string | undefined) ?? "/app/").replace(
  /\/$/,
  ""
);

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter basename={basename}>
          <Routes>
            <Route path="/" element={<RegionRedirect />} />
            <Route path="/events/:eventId" element={<EventDetailPage />} />
            <Route
              path="/admin"
              element={
                <ProtectedRoute>
                  <AdminPage />
                </ProtectedRoute>
              }
            />
            <Route path="/:region" element={<EventsListPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
