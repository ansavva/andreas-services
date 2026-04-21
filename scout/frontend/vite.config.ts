import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// VITE_BASE controls the public path the SPA is served under.
// Prod (scout.andreas.services):          VITE_BASE=/app/
// PR preview (scout-pr.andreas.services): VITE_BASE=/<PR_NUMBER>/app/
// Local dev falls back to /app/.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/app/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
