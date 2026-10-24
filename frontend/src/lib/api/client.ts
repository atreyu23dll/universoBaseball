/** Cliente HTTP de la API. Un sitio para los errores y las cabeceras. */

import type { ApiError } from './types';

const BASE = '/api/v1';

export class RequestFailed extends Error {
  readonly code: string;
  readonly suggestions: string[];
  readonly status: number;

  constructor(status: number, body: ApiError | null, fallback: string) {
    super(body?.message ?? fallback);
    this.status = status;
    this.code = body?.code ?? 'http_error';
    this.suggestions = body?.suggestions ?? [];
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) }
  });
  if (!response.ok) {
    let body: ApiError | null = null;
    try {
      body = (await response.json()) as ApiError;
    } catch {
      body = null;
    }
    throw new RequestFailed(response.status, body, `${response.status} en ${path}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
      headers
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body === undefined ? undefined : JSON.stringify(body)
    }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' })
};

/** Clave de idempotencia estable para que un reintento no duplique un avance. */
export function idempotencyKey(universeId: string, action: string): string {
  return `${universeId}:${action}:${Date.now()}`;
}
