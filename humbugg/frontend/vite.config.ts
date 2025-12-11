import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const isProduction = process.env.NODE_ENV === 'production';
const basePath = isProduction ? process.env.VITE_APP_BASE_PATH || '/app/' : '/';

export default defineConfig({
  base: basePath,
  plugins: [react()],
  server: {
    port: Number(process.env.PORT || 5173),
    open: true
  }
});
