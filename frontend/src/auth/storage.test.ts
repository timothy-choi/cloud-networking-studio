import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CNS_ACCESS_TOKEN_KEY,
  CNS_SELECTED_PROJECT_KEY,
  clearAuthSessionStorage,
  getStoredAccessToken,
  setStoredAccessToken,
} from './storage';

function mockWebStorage() {
  const local: Record<string, string> = {};
  const session: Record<string, string> = {};
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => local[k] ?? null,
    setItem: (k: string, v: string) => {
      local[k] = v;
    },
    removeItem: (k: string) => {
      delete local[k];
    },
  });
  vi.stubGlobal('sessionStorage', {
    getItem: (k: string) => session[k] ?? null,
    setItem: (k: string, v: string) => {
      session[k] = v;
    },
    removeItem: (k: string) => {
      delete session[k];
    },
  });
  return { local, session };
}

describe('auth token persistence', () => {
  beforeEach(() => {
    mockWebStorage();
  });

  it('stores JWT in localStorage', () => {
    setStoredAccessToken('jwt-abc');
    expect(localStorage.getItem(CNS_ACCESS_TOKEN_KEY)).toBe('jwt-abc');
    expect(sessionStorage.getItem(CNS_ACCESS_TOKEN_KEY)).toBeNull();
    expect(getStoredAccessToken()).toBe('jwt-abc');
  });

  it('migrates legacy sessionStorage token to localStorage', () => {
    sessionStorage.setItem(CNS_ACCESS_TOKEN_KEY, 'legacy-tok');
    expect(getStoredAccessToken()).toBe('legacy-tok');
    expect(localStorage.getItem(CNS_ACCESS_TOKEN_KEY)).toBe('legacy-tok');
    expect(sessionStorage.getItem(CNS_ACCESS_TOKEN_KEY)).toBeNull();
  });

  it('clearAuthSessionStorage removes token and selected project', () => {
    localStorage.setItem(CNS_ACCESS_TOKEN_KEY, 'tok');
    sessionStorage.setItem(CNS_SELECTED_PROJECT_KEY, 'proj-1');
    clearAuthSessionStorage();
    expect(localStorage.getItem(CNS_ACCESS_TOKEN_KEY)).toBeNull();
    expect(sessionStorage.getItem(CNS_SELECTED_PROJECT_KEY)).toBeNull();
  });

  it('setStoredAccessToken(null) clears persisted token', () => {
    setStoredAccessToken('tok');
    setStoredAccessToken(null);
    expect(getStoredAccessToken()).toBeNull();
  });
});
