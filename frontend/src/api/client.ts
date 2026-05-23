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

export function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (raw !== undefined && raw.trim() !== '') {
    return raw.replace(/\/$/, '');
  }
  // `vite` dev server: same-origin `/api` proxied to FastAPI (see vite.config.ts).
  if (import.meta.env.DEV) {
    return '/api';
  }
  // `vite preview` (default port 4173): same proxy as dev.
  if (typeof window !== 'undefined' && window.location.port === '4173') {
    return '/api';
  }
  // Production static build behind Caddy/nginx: same-origin `/api` unless VITE_API_BASE_URL is set.
  if (import.meta.env.PROD) {
    return '/api';
  }
  return 'http://localhost:8000';
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBase()}${path.startsWith('/') ? path : `/${path}`}`;
  const token = getStoredAccessToken();
  const headers: HeadersInit = {
    Accept: 'application/json',
    ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    ...(init?.headers ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(url, { ...init, headers });

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

function extractRequestId(detail: unknown): string | null {
  const structured = parseStructuredError(detail);
  return structured?.request_id ?? null;
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
    const m = err.message;
    if (
      m === 'Failed to fetch' ||
      m.includes('NetworkError') ||
      m.includes('Load failed')
    ) {
      return `${m} — cannot reach ${getApiBase()}. Start the API on port 8000 (see README), or keep using dev defaults so Vite proxies /api → 127.0.0.1:8000.`;
    }
    return m;
  }
  return String(err);
}

function _isLikelyNetworkError(err: Error): boolean {
  const m = err.message;
  return m === 'Failed to fetch' || m.includes('NetworkError') || m.includes('Load failed');
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
