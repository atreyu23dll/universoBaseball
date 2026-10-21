import { sveltekit } from '@sveltejs/kit/vite';
import type { UserConfig } from 'vite';

// El reenvío a la API lo hace `src/routes/api/[...path]/+server.ts`, no un
// proxy de Vite: así desarrollo y producción recorren exactamente el mismo
// camino. El destino se configura con la variable `BU_API_URL`.
const config: UserConfig = {
  plugins: [sveltekit()],
  server: {
    host: '127.0.0.1',
    port: 5173
  }
};

export default config;
