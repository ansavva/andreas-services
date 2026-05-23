import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@/context/ThemeContext";
import { EventsListPage } from "@/pages/EventsListPage";
import { EventDetailPage } from "@/pages/EventDetailPage";
import "@/index.css";

// Strip trailing slash so React Router's basename is well-formed (e.g. "/app" not "/app/")
const basename = ((import.meta.env.VITE_BASE as string | undefined) ?? "/app/").replace(
  /\/$/,
  ""
);

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter basename={basename}>
        <Routes>
          <Route path="/" element={<EventsListPage />} />
          <Route path="/events/:eventId" element={<EventDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
