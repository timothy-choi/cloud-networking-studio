import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  apiFetch,
  ApiParseError,
  formatApiError,
  formatNetworkReachabilityError,
  isAbsoluteApiBase,
  resolveApiBaseFromEnv,
} from './client';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('resolveApiBaseFromEnv', () => {
  it('dev ignores absolute production URL and uses Vite proxy', () => {
    expect(
      resolveApiBaseFromEnv({
        dev: true,
        prod: false,
        viteApiBaseUrl: 'https://api.cloudnetstudio.com/api',
      }),
    ).toBe('/api');
  });

  it('dev honors relative VITE_API_BASE_URL', () => {
    expect(
      resolveApiBaseFromEnv({
        dev: true,
        prod: false,
        viteApiBaseUrl: '/api',
      }),
    ).toBe('/api');
  });

  it('dev allows remote API when VITE_USE_REMOTE_API is true', () => {
    expect(
      resolveApiBaseFromEnv({
        dev: true,
        prod: false,
        viteApiBaseUrl: 'https://api.cloudnetstudio.com/api',
        useRemoteApi: true,
      }),
    ).toBe('https://api.cloudnetstudio.com/api');
  });

  it('production uses configured absolute API base', () => {
    expect(
      resolveApiBaseFromEnv({
        dev: false,
        prod: true,
        viteApiBaseUrl: 'https://api.cloudnetstudio.com/api',
      }),
    ).toBe('https://api.cloudnetstudio.com/api');
  });

  it('production defaults to same-origin /api', () => {
    expect(
      resolveApiBaseFromEnv({
        dev: false,
        prod: true,
      }),
    ).toBe('/api');
  });

  it('vite preview defaults to /api', () => {
    expect(
      resolveApiBaseFromEnv({
        dev: false,
        prod: false,
        previewPort: '4173',
        viteApiBaseUrl: 'https://api.cloudnetstudio.com/api',
      }),
    ).toBe('/api');
  });
});

describe('resolveApiUrl', () => {
  it('joins base and path without double slashes', () => {
    const base = resolveApiBaseFromEnv({ dev: true, prod: false });
    expect(`${base}/api-tokens`).toBe('/api/api-tokens');
  });
});

describe('isAbsoluteApiBase', () => {
  it('detects http(s) bases', () => {
    expect(isAbsoluteApiBase('https://api.cloudnetstudio.com/api')).toBe(true);
    expect(isAbsoluteApiBase('/api')).toBe(false);
  });
});

describe('formatNetworkReachabilityError', () => {
  it('mentions resolved base without secrets', () => {
    const msg = formatNetworkReachabilityError(new Error('Failed to fetch'));
    expect(msg).toContain('Failed to fetch');
    expect(msg).not.toMatch(/Bearer|token/i);
  });

  it('distinguishes aborted requests from reachability failures', () => {
    const err = new DOMException('The operation was aborted.', 'AbortError');
    const msg = formatApiError(err);
    expect(msg).toContain('Request was aborted');
    expect(msg).toContain('Endpoint base:');
  });
});

describe('apiFetch', () => {
  it('throws a parse error with response context for invalid JSON success bodies', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response('not-json', {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        ),
      ),
    );

    await expect(apiFetch('/topologies/topo-1/ai-infrastructure-advice')).rejects.toBeInstanceOf(
      ApiParseError,
    );
  });

  it('formats parse errors with HTTP status, endpoint, and body snippet', () => {
    const msg = formatApiError(new ApiParseError(200, 'OK', '/api/example', 'not-json', new Error('bad')));
    expect(msg).toContain('API response could not be parsed as JSON.');
    expect(msg).toContain('HTTP 200 OK');
    expect(msg).toContain('Endpoint: /api/example');
    expect(msg).toContain('Response body: not-json');
  });
});
