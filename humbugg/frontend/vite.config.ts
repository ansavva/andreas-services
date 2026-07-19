import { reactRouter } from '@react-router/dev/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// Vitest can't run the React Router dev plugin: it injects an HMR "preamble"
// that the jsdom test environment never provides, so any rendered component
// throws "React Router Vite plugin can't detect preamble." Under Vitest we drop
// the framework/tailwind plugins and let esbuild's automatic JSX runtime
// (matching tsconfig "jsx": "react-jsx") transform components for @testing-library.
const isVitest = !!process.env.VITEST;

export default defineConfig(({ command }) => ({
  plugins: isVitest ? [] : [tailwindcss(), reactRouter()],
  esbuild: isVitest ? { jsx: 'automatic' } : undefined,
  resolve: { tsconfigPaths: true },
  ssr: {
    noExternal: command === 'build'
      ? [
          '@ansavva/design-system',
          /^@base-ui\//,
          /^@floating-ui\//,
          '@babel/runtime',
          'use-sync-external-store',
          'clsx',
          'tailwind-merge',
        ]
      : [],
  },
  server: {
    port: Number(process.env.PORT || 5173),
    open: true,
    proxy: {
      '/api': 'http://127.0.0.1:5001',
      '/health': 'http://127.0.0.1:5001',
    },
  },
}));
