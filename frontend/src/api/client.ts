/** Typed fetch helper + API base from Vite env. */

import type { ControllerStatusResponse, HealthResponse } from '../types/health';

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly detail: unknown;

  constructor(status: number, statusText: string, detail: unknown) {
    super(`${status} ${statusText}`);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
  }
}

export function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
  return raw.replace(/\/$/, '');
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBase()}${path.startsWith('/') ? path : `/${path}`}`;
  const headers: HeadersInit = {
    Accept: 'application/json',
    ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    ...(init?.headers ?? {}),
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
    throw new ApiError(res.status, res.statusText, detail);
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

export function formatApiError(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.detail as { detail?: unknown };
    if (typeof d?.detail === 'string') return d.detail;
    if (Array.isArray(d?.detail)) {
      return d.detail.map((x: unknown) => JSON.stringify(x)).join('; ');
    }
    if (d?.detail != null) return JSON.stringify(d.detail);
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health');
}

export async function getControllerStatus(): Promise<ControllerStatusResponse> {
  return apiFetch<ControllerStatusResponse>('/controller/status');
}
