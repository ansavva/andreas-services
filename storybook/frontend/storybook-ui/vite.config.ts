import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tsconfigPaths(), tailwindcss()],
  base: '/app/',
  // :5177 — every service's dev ports are one table in the root CLAUDE.md.
  server: { port: 5177, strictPort: true },
})
