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

  // What is tested here is addressing, in both directions.
  //
  // The route table (`src/routes.test.tsx`) and the URL helpers
  // (`src/utils/location.test.ts`) pin which screen a URL reaches; the API
  // wrappers (`src/apis/studio.test.ts`) and `NodeAddressing.test.tsx` pin which
  // *string* a call site sends. Both are the same class of failure and it is the
  // opposite of every other failure in this app: a broken listing is a blank
  // page and somebody reports it, while a wrong route renders the wrong screen
  // confidently and a wrong address signs the wrong object. A row carries both
  // an `id` and a `key` and both are `string`, so a type cannot catch the swap.
  //
  // The rest of the frontend is covered by typecheck and the build, and that is
  // stated in `docs/WEB_APP.md` rather than implied.
  //
  // `jsdom` because two of those are components: what is being asserted is that
  // they navigate, or fetch, to the right place, and there is no smaller unit
  // that says so. `clearMocks` and `restoreMocks` together so neither a stubbed
  // call *count* nor its stubbed answer leaks into the next case — "it was not
  // called" is one of the assertions, and it is worthless against a shared tally.
  //
  // `setupFiles` fills in two browser APIs this jsdom does not have —
  // `localStorage` and `CSS.escape` — which are the environment's gaps rather
  // than the app's. See `src/test-setup.ts`.
  //
  // COVERAGE IS REPORTED AND GATED ON NOTHING, and here that is not a compromise
  // — it is the paragraph above, expressed as a number. A suite that deliberately
  // tests addressing and leaves the rest to typecheck and the build SHOULD score
  // low, and a threshold would either be set below the real figure (meaning
  // nothing) or push somebody into writing render tests this file argues against.
  // What the number is for is noticing a direction of travel over months.
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    clearMocks: true,
    restoreMocks: true,
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text-summary"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test-setup.ts", "src/main.tsx",
                "src/vite-env.d.ts", "src/**/*.d.ts"],
    },
  },
});
