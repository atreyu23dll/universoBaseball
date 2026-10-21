/**
 * Proxy de la API en el propio servidor de SvelteKit.
 *
 * Existe para que el navegador hable **siempre con el mismo origen**, tanto en
 * `vite dev` como en la compilación de producción que corre con el adaptador de
 * Node dentro del contenedor. Antes esto lo hacía el proxy de Vite, que solo
 * existe en desarrollo: en Docker el navegador pedía `/api/v1/...` al servidor
 * de SvelteKit, que no tiene esa ruta, y recibía un 404 con el HTML de la
 * página. Un solo camino, en los dos entornos.
 *
 * Efecto secundario deseable: la interfaz no depende de CORS.
 */

import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const DEFAULT_TARGET = 'http://127.0.0.1:8000';

/** Cabeceras que se reenvían. `Idempotency-Key` es imprescindible: sin ella un
 *  reintento del avance del reloj duplicaría la simulación. */
const FORWARDED = ['content-type', 'accept', 'idempotency-key'];

const proxy: RequestHandler = async ({ request, params, url }) => {
  const base = (env.BU_API_URL ?? DEFAULT_TARGET).replace(/\/$/, '');
  const target = `${base}/api/${params.path ?? ''}${url.search}`;

  const headers = new Headers();
  for (const name of FORWARDED) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const init: RequestInit = { method: request.method, headers };
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = await request.text();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (error) {
    // La API no responde. Se devuelve un error con la forma que la interfaz ya
    // sabe mostrar, en vez de dejar que el fallo salga como un 500 opaco.
    return json(
      {
        code: 'api_unreachable',
        message: `No se pudo contactar con la API en ${base}: ${
          error instanceof Error ? error.message : String(error)
        }`,
        suggestions: [
          'comprueba que el servicio `api` está arriba (docker compose ps)',
          'en desarrollo sin Docker, arranca la API con `make run-api`'
        ]
      },
      502
    );
  }

  // 204 y 304 no llevan cuerpo; construir una respuesta con body las rompe.
  const body = upstream.status === 204 || upstream.status === 304 ? null : await upstream.arrayBuffer();
  const responseHeaders = new Headers();
  const contentType = upstream.headers.get('content-type');
  if (contentType) responseHeaders.set('content-type', contentType);

  return new Response(body, { status: upstream.status, headers: responseHeaders });
};

function json(payload: unknown, status: number): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' }
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
