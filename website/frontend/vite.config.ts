import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tailwindcss(), reactRouter()],
  // Vite 8 resolves tsconfig `paths` natively.
  resolve: { tsconfigPaths: true },
  ssr: {
    // Bundle the private design system and its entire (dev-only) UI dependency
    // subtree into the server build, so the runtime Lambda image needs neither
    // the GitHub Packages registry nor these transitive packages installed.
    // Everything here is pulled in via @ansavva/design-system → Base UI.
    noExternal: [
      "@ansavva/design-system",
      /^@base-ui\//,
      /^@floating-ui\//,
      "@babel/runtime",
      "use-sync-external-store",
      "clsx",
      "tailwind-merge",
    ],
  },
});
