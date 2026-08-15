import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// @ansavva/design-system re-exports an extensionless "./button" and leaves leaf
// selection to the consumer, so the bundler picks `.web.tsx` here and Metro
// picks `.native.tsx` elsewhere. Vite's default `resolve.extensions` stop at
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
  // whatever compiles the app has to transform it too; without this the build
  // fails on a type annotation or JSX *inside* node_modules. The dependency
  // optimizer resolves separately from `resolve`, so the leaf order has to be
  // repeated here or it cannot find a single component.
  optimizeDeps: {
    include: ["@ansavva/design-system"],
    rollupOptions: { resolve: { extensions: webFirstExtensions } },
  },
  server: { port: 5173 },
});
