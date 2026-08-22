import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";

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

  // There is one thing under test and it is the legacy-URL resolver. A share
  // link that quietly stops working is invisible until somebody reports it,
  // which is the opposite of every other failure in this app — a broken listing
  // is a blank page. The rest of the frontend is covered by typecheck and the
  // build, and that is stated in `docs/WEB_APP.md` rather than implied.
  //
  // `jsdom` because the resolver is a component: what is being asserted is that
  // it navigates, once, to the right place, and there is no smaller unit that
  // says that. `clearMocks` and `restoreMocks` together so neither a stubbed
  // `apis/studio` call *count* nor its stubbed answer leaks into the next case —
  // "the resolver was not called" is one of the assertions, and it is worthless
  // against a shared tally.
  //
  // `setupFiles` fills in two browser APIs this jsdom does not have —
  // `localStorage` and `CSS.escape` — which are the environment's gaps rather
  // than the app's. See `src/test-setup.ts`.
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    clearMocks: true,
    restoreMocks: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
