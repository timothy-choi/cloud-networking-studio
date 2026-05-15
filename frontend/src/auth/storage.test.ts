import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CNS_ACCESS_TOKEN_KEY,
  CNS_SELECTED_PROJECT_KEY,
  clearAuthSessionStorage,
} from './storage';

describe('clearAuthSessionStorage', () => {
  const mem: Record<string, string> = {};

  beforeEach(() => {
    mem[CNS_ACCESS_TOKEN_KEY] = 'tok';
    mem[CNS_SELECTED_PROJECT_KEY] = 'proj-1';
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => mem[k] ?? null,
      setItem: (k: string, v: string) => {
        mem[k] = v;
      },
      removeItem: (k: string) => {
        delete mem[k];
      },
    });
  });

  it('removes JWT and selected-project keys', () => {
    clearAuthSessionStorage();
    expect(sessionStorage.getItem(CNS_ACCESS_TOKEN_KEY)).toBeNull();
    expect(sessionStorage.getItem(CNS_SELECTED_PROJECT_KEY)).toBeNull();
  });
});
