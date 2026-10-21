import { sveltekit } from '@sveltejs/kit/vite';
import type { UserConfig } from 'vite';

const apiTarget = process.env.BU_API_URL ?? 'http://127.0.0.1:8000';

const config: UserConfig = {
  plugins: [sveltekit()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    // Proxy en desarrollo: el navegador habla con el mismo origen y no hay CORS.
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      '/health': { target: apiTarget, changeOrigin: true }
    }
  }
};

export default config;
