import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";

// @ansavva/design-system re-exports an extensionless "./button" and leaves leaf
// selection to the consumer. Vite's default `resolve.extensions` stop at
// `.tsx`, which makes every one of those re-exports resolve to nothing — the
// web-suffixed forms have to come first. `tsconfig.json`'s `moduleSuffixes`
// mirrors this order for tsc.
const webFirstExtensions = [
  ".web.tsx",
  ".web.ts",
  ".web.jsx",
  ".web.js",
  ".mjs",
  ".js",
  ".mts",
  ".ts",
  ".jsx",
  ".tsx",
  ".json",
];

export default defineConfig({
  plugins: [tailwindcss(), react()],
  resolve: { extensions: webFirstExtensions },
  // The design system publishes TypeScript source with no build step, so
  // whatever compiles the app has to transform it too. The dependency
  // optimizer resolves separately from `resolve`, so the leaf order is
  // repeated here or it cannot find a single component.
  optimizeDeps: {
    include: ["@ansavva/design-system"],
    rollupOptions: { resolve: { extensions: webFirstExtensions } },
  },
  server: { port: 5174 },

  // What is tested here is the two things a type cannot catch: that the PKCE
  // challenge is still on the authorize URL (Cognito has no server-side
  // "require PKCE" toggle, so this file is the only thing enforcing it), and
  // that the reader renders a published page's HTML rather than escaping it.
  // The rest is covered by typecheck and the build.
  test: {
    environment: "jsdom",
    clearMocks: true,
    restoreMocks: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
