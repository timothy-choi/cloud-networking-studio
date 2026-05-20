import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

/** Backend for dev/preview proxy — use 127.0.0.1 to avoid IPv6 localhost mismatches. */
const apiProxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000';

const apiProxy = {
  '/api': {
    target: apiProxyTarget,
    changeOrigin: true,
    ws: true,
    rewrite: (path: string) => path.replace(/^\/api/, '') || '/',
  },
} as const;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
});
