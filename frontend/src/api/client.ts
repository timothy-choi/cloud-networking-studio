/** Typed fetch helper + API base from Vite env. */

import { getStoredAccessToken, setStoredAccessToken } from '../auth/storage';
import type { ControllerStatusResponse, HealthResponse } from '../types/health';

export { getStoredAccessToken, setStoredAccessToken };

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly detail: unknown;
  readonly requestId: string | null;

  constructor(status: number, statusText: string, detail: unknown, requestId: string | null = null) {
    super(`${status} ${statusText}`);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
    this.requestId = requestId;
  }
}

export interface StructuredApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string | null;
}

export function parseStructuredError(detail: unknown): StructuredApiError | null {
  if (!detail || typeof detail !== 'object') return null;
  const d = detail as Record<string, unknown>;
  const err = d.error as Record<string, unknown> | undefined;
  if (err && typeof err.code === 'string') {
    return {
      code: err.code,
      message: String(err.message ?? d.detail ?? ''),
      details: (err.details as Record<string, unknown>) ?? {},
      request_id: (err.request_id as string | null) ?? (d.request_id as string | null) ?? null,
    };
  }
  return null;
}

export type ApiBaseContext = {
  dev: boolean;
  prod: boolean;
  viteApiBaseUrl?: string;
  useRemoteApi?: boolean;
  previewPort?: string;
};

function normalizeApiBase(raw: string): string {
  return raw.trim().replace(/\/$/, '');
}

export function isAbsoluteApiBase(base: string): boolean {
  return /^https?:\/\//i.test(base);
}

/** Pure resolver for tests and runtime. */
export function resolveApiBaseFromEnv(ctx: ApiBaseContext): string {
  const trimmed = (ctx.viteApiBaseUrl ?? '').trim();

  // Vite dev server: same-origin `/api` proxy unless explicitly testing a remote API.
  if (ctx.dev) {
    if (ctx.useRemoteApi && trimmed) {
      return normalizeApiBase(trimmed);
    }
    if (trimmed.startsWith('/')) {
      return normalizeApiBase(trimmed);
    }
    return '/api';
  }

  // `vite preview` uses the same proxy as dev.
  if (ctx.previewPort === '4173') {
    if (trimmed && !isAbsoluteApiBase(trimmed)) {
      return normalizeApiBase(trimmed);
    }
    return '/api';
  }

  // Production static bundle (Vercel, Caddy on EC2, etc.).
  if (trimmed) {
    return normalizeApiBase(trimmed);
  }
  if (ctx.prod) {
    return '/api';
  }
  return '/api';
}

export function getApiBase(): string {
  return resolveApiBaseFromEnv({
    dev: import.meta.env.DEV,
    prod: import.meta.env.PROD,
    viteApiBaseUrl: import.meta.env.VITE_API_BASE_URL as string | undefined,
    useRemoteApi: import.meta.env.VITE_USE_REMOTE_API === 'true',
    previewPort: typeof window !== 'undefined' ? window.location.port : undefined,
  });
}

export function resolveApiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${getApiBase()}${normalizedPath}`;
}

export function resolveApiWebSocketUrl(pathWithQuery: string): string {
  const path = pathWithQuery.startsWith('/') ? pathWithQuery : `/${pathWithQuery}`;
  const base = getApiBase().replace(/\/$/, '');
  if (base.startsWith('/')) {
    const wsProto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = typeof window !== 'undefined' ? window.location.host : 'localhost';
    return `${wsProto}//${host}${base}${path}`;
  }
  const wsBase = base.replace(/^http/i, 'ws');
  return `${wsBase}${path}`;
}

function buildAuthHeaders(init?: RequestInit): HeadersInit {
  const token = getStoredAccessToken();
  return {
    Accept: 'application/json',
    ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    ...(init?.headers ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveApiUrl(path);
  const res = await fetch(url, { ...init, headers: buildAuthHeaders(init) });

  if (!res.ok) {
    let detail: unknown;
    const text = await res.text();
    try {
      detail = text ? JSON.parse(text) : null;
    } catch {
      detail = text;
    }
    throw new ApiError(res.status, res.statusText, detail, extractRequestId(detail));
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const ct = res.headers.get('content-type');
  if (!ct?.includes('application/json')) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export async function apiFetchBlob(path: string, init?: RequestInit): Promise<Blob> {
  const url = resolveApiUrl(path);
  const token = getStoredAccessToken();
  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(String(detail));
    } catch {
      /* plain text error */
    }
    throw new ApiError(res.status, res.statusText, detail);
  }
  return res.blob();
}

function extractRequestId(detail: unknown): string | null {
  const structured = parseStructuredError(detail);
  return structured?.request_id ?? null;
}

function _isLikelyNetworkError(err: Error): boolean {
  const m = err.message;
  return m === 'Failed to fetch' || m.includes('NetworkError') || m.includes('Load failed');
}

export function formatNetworkReachabilityError(err: Error): string {
  const base = getApiBase();
  if (import.meta.env.DEV && isAbsoluteApiBase(base)) {
    return `${err.message} — resolved API base is ${base}. In local dev, use the Vite proxy at /api (remove absolute VITE_API_BASE_URL from frontend/.env, or set VITE_USE_REMOTE_API=true to call a remote API intentionally).`;
  }
  if (import.meta.env.DEV) {
    return `${err.message} — cannot reach ${base}. Start the API on port 8000 (see README), or keep dev defaults so Vite proxies /api → 127.0.0.1:8000.`;
  }
  return `${err.message} — cannot reach ${base}. Confirm the API is running and CORS allows this app origin.`;
}

export function formatApiError(err: unknown): string {
  if (err instanceof ApiError) {
    const structured = parseStructuredError(err.detail);
    if (structured?.code === 'RATE_LIMITED') {
      return structured.message || 'Too many requests. Please wait a moment and try again.';
    }
    if (structured?.code === 'QUOTA_EXCEEDED') {
      return structured.message || 'Quota limit reached for this project or account.';
    }
    if (structured?.message) return structured.message;
    const d = err.detail as { detail?: unknown };
    if (typeof d?.detail === 'string') return d.detail;
    if (Array.isArray(d?.detail)) {
      return d.detail.map((x: unknown) => JSON.stringify(x)).join('; ');
    }
    if (d?.detail != null) return JSON.stringify(d.detail);
    return err.message;
  }
  if (err instanceof Error) {
    if (_isLikelyNetworkError(err)) {
      return formatNetworkReachabilityError(err);
    }
    return err.message;
  }
  return String(err);
}

const _LOGIN_GENERIC =
  'Something went wrong. Please try again in a moment.';

/** Login form: uniform copy for bad credentials; generic message for server/network issues. */
export function formatLoginError(err: unknown): string {
  if (err instanceof ApiError && err.status === 401) {
    return 'Invalid email or password';
  }
  if (err instanceof ApiError && err.status >= 500) {
    return _LOGIN_GENERIC;
  }
  if (err instanceof Error && _isLikelyNetworkError(err)) {
    return _LOGIN_GENERIC;
  }
  return formatApiError(err);
}

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health');
}

export async function getControllerStatus(): Promise<ControllerStatusResponse> {
  return apiFetch<ControllerStatusResponse>('/controller/status');
}
