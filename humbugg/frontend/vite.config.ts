import { reactRouter } from '@react-router/dev/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig(({ command }) => ({
  plugins: [tailwindcss(), reactRouter()],
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
