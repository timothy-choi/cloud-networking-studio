/** Typed fetch helper + API base from Vite env. */

import { getStoredAccessToken, setStoredAccessToken } from '../auth/storage';
import type { ControllerStatusResponse, HealthResponse } from '../types/health';

export { getStoredAccessToken, setStoredAccessToken };

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly detail: unknown;
  readonly requestId: string | null;
  readonly url: string;

  constructor(
    status: number,
    statusText: string,
    detail: unknown,
    requestId: string | null = null,
    url: string = '',
  ) {
    super(`${status} ${statusText}`);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
    this.requestId = requestId;
    this.url = url;
  }
}

export class ApiParseError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly url: string;
  readonly responseText: string;
  readonly cause: unknown;

  constructor(status: number, statusText: string, url: string, responseText: string, cause: unknown) {
    super(`Failed to parse API response from ${url}`);
    this.name = 'ApiParseError';
    this.status = status;
    this.statusText = statusText;
    this.url = url;
    this.responseText = responseText;
    this.cause = cause;
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

type ApiFetchInit = RequestInit & {
  debugLabel?: string;
};

function debugApiFetch(label: string | undefined, message: string, payload?: unknown) {
  if (!label) return;
  // Temporary Step 61 regression diagnostics: the UI collapsed browser fetch/parse failures into
  // a generic reachability message, hiding whether the advisor returned HTTP, body, or JSON errors.
  // Do not log request headers or bearer tokens.
  console.debug(`[apiFetch:${label}] ${message}`, payload);
}

export async function apiFetch<T>(path: string, init?: ApiFetchInit): Promise<T> {
  const { debugLabel, ...fetchInit } = init ?? {};
  const url = resolveApiUrl(path);
  debugApiFetch(debugLabel, 'request', {
    method: fetchInit.method ?? 'GET',
    url,
    hasBody: Boolean(fetchInit.body),
  });

  let res: Response;
  try {
    res = await fetch(url, { ...fetchInit, headers: buildAuthHeaders(fetchInit) });
  } catch (err) {
    debugApiFetch(debugLabel, 'fetch threw before an HTTP response was available', err);
    throw err;
  }

  const contentType = res.headers.get('content-type');
  debugApiFetch(debugLabel, 'response status', {
    status: res.status,
    statusText: res.statusText,
    contentType,
  });

  if (!res.ok) {
    let detail: unknown;
    const text = await res.text();
    debugApiFetch(debugLabel, 'error response body', text);
    try {
      detail = text ? JSON.parse(text) : null;
    } catch {
      detail = text;
    }
    debugApiFetch(debugLabel, 'parsed error response', detail);
    throw new ApiError(res.status, res.statusText, detail, extractRequestId(detail), url);
  }

  if (res.status === 204) {
    debugApiFetch(debugLabel, 'empty response', null);
    return undefined as T;
  }

  if (!contentType?.includes('application/json')) {
    debugApiFetch(debugLabel, 'non-json success response', { contentType });
    return undefined as T;
  }

  const text = await res.text();
  debugApiFetch(debugLabel, 'success response body', text);
  try {
    const parsed = text ? (JSON.parse(text) as T) : (undefined as T);
    debugApiFetch(debugLabel, 'parsed success response', parsed);
    return parsed;
  } catch (err) {
    debugApiFetch(debugLabel, 'json parse failed', err);
    throw new ApiParseError(res.status, res.statusText, url, text, err);
  }
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
    throw new ApiError(res.status, res.statusText, detail, extractRequestId(detail), url);
  }
  return res.blob();
}

function extractRequestId(detail: unknown): string | null {
  const structured = parseStructuredError(detail);
  return structured?.request_id ?? null;
}

function _isLikelyNetworkError(err: Error): boolean {
  const m = err.message;
  return (
    err.name === 'AbortError' ||
    err.name === 'TimeoutError' ||
    m === 'Failed to fetch' ||
    m.includes('NetworkError') ||
    m.includes('Load failed')
  );
}

export function formatNetworkReachabilityError(err: Error): string {
  const base = getApiBase();
  if (err.name === 'AbortError') {
    return `Request was aborted before the API returned a response. Endpoint base: ${base}.`;
  }
  if (err.name === 'TimeoutError') {
    return `Request timed out before the API returned a response. Endpoint base: ${base}.`;
  }
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

    const lines: string[] = [];
    if (structured?.message) {
      lines.push(structured.message);
    } else {
      const d = err.detail as { detail?: unknown; message?: unknown };
      if (typeof d?.message === 'string') {
        lines.push(d.message);
      } else if (typeof d?.detail === 'string') {
        lines.push(d.detail);
      } else if (Array.isArray(d?.detail)) {
        lines.push(d.detail.map((x: unknown) => JSON.stringify(x)).join('; '));
      } else if (d?.detail != null) {
        lines.push(JSON.stringify(d.detail));
      } else {
        lines.push(err.message);
      }
    }

    lines.push(`HTTP ${err.status} ${err.statusText}`);
    if (err.url) {
      lines.push(`Endpoint: ${err.url}`);
    }
    const requestId = structured?.request_id ?? err.requestId;
    if (requestId) {
      lines.push(`Request ID: ${requestId}`);
    }
    return lines.join('\n');
  }
  if (err instanceof ApiParseError) {
    const snippet =
      err.responseText.length > 400 ? `${err.responseText.slice(0, 400)}...` : err.responseText;
    return [
      'API response could not be parsed as JSON.',
      `HTTP ${err.status} ${err.statusText}`,
      `Endpoint: ${err.url}`,
      snippet ? `Response body: ${snippet}` : 'Response body was empty.',
    ].join('\n');
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
