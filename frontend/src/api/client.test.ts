import { describe, expect, it } from 'vitest';

import {
  formatNetworkReachabilityError,
  isAbsoluteApiBase,
  resolveApiBaseFromEnv,
} from './client';

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
});
