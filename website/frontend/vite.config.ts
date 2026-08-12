import { reactRouter } from "@react-router/dev/vite";
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

export default defineConfig(({ command }) => ({
  plugins: [tailwindcss(), reactRouter()],
  // Vite 8 resolves tsconfig `paths` natively.
  resolve: { tsconfigPaths: true, extensions: webFirstExtensions },
  // The design system publishes TypeScript source with no build step, so
  // whatever compiles the app has to transform it too; without this the build
  // fails on a type annotation or JSX *inside* node_modules. The dependency
  // optimizer resolves separately from `resolve`, so the leaf order has to be
  // repeated here or it cannot find a single component.
  optimizeDeps: {
    include: ["@ansavva/design-system"],
    rollupOptions: { resolve: { extensions: webFirstExtensions } },
  },
  ssr: {
    // Only for the production build: bundle the private design system and its
    // runtime dependencies into the server build, so the runtime Lambda image
    // needs neither the GitHub Packages registry nor these transitive packages
    // installed. In dev they stay external and load normally from node_modules
    // (bundling CJS deps breaks Vite's dev SSR module runner).
    noExternal:
      command === "build"
        ? ["@ansavva/design-system", "clsx", "tailwind-merge"]
        : [],
  },
}));
