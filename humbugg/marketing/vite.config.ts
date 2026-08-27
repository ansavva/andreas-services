import { reactRouter } from '@react-router/dev/vite';
import tailwindcss from '@tailwindcss/vite';
// vitest/config, not vite: same defineConfig plus the typed `test` block below.
import { defineConfig } from 'vitest/config';

// Vitest can't run the React Router dev plugin: it injects an HMR "preamble"
// that the jsdom test environment never provides, so any rendered component
// throws "React Router Vite plugin can't detect preamble." Under Vitest we drop
// the framework/tailwind plugins; Vite's transformer emits the automatic JSX
// runtime from tsconfig ("jsx": "react-jsx"), which is all the tests need.
const isVitest = !!process.env.VITEST;

// The package re-exports an extensionless "./button" and leaves leaf selection
// to the consumer. Vite's defaults stop at `.tsx`, so the web-suffixed forms go
// first — otherwise every component is unresolved. tsconfig.json's
// `moduleSuffixes` is the same order for tsc.
const webFirstExtensions = ['.web.tsx', '.web.ts', '.web.jsx', '.web.js', '.mjs', '.js', '.mts', '.ts', '.jsx', '.tsx', '.json'];

export default defineConfig(({ command }) => ({
  plugins: isVitest ? [] : [tailwindcss(), reactRouter()],
  // Runtime .env.local values must not alter tests that assert production-safe defaults.
  envDir: isVitest ? false : undefined,
  resolve: { tsconfigPaths: true, extensions: webFirstExtensions },
  // @ansavva/design-system publishes TypeScript source with no build step, so
  // whatever compiles the app has to transform it too; without this the build
  // fails on a type annotation or JSX inside node_modules. The dependency
  // optimizer resolves separately from `resolve`, so it needs the leaf order
  // repeated or it cannot find a single component.
  optimizeDeps: {
    include: ['@ansavva/design-system'],
    rollupOptions: { resolve: { extensions: webFirstExtensions } },
  },
  ssr: {
    noExternal: command === 'build'
      ? ['@ansavva/design-system', 'clsx', 'tailwind-merge']
      : [],
  },
  server: {
    port: Number(process.env.PORT || 5173),
    open: true,
  },
  test: {
    environment: 'jsdom',
    // Testing Library registers its between-test cleanup on a global afterEach;
    // without globals every second render finds the first one still mounted.
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    // Styles carry no assertions here; parsing Tailwind output in jsdom is pure cost.
    css: false,
    include: ['src/**/*.test.{ts,tsx}', 'app/**/*.test.{ts,tsx}'],
    // "it was not called" is one of the assertions, and it is worthless
    // against a shared tally.
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text-summary'],
      include: ['src/**/*.{ts,tsx}', 'app/**/*.{ts,tsx}'],
      exclude: ['**/*.test.{ts,tsx}', 'app/assets/**'],
    },
  },
}));
