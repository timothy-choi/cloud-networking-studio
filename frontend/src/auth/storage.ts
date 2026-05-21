/** Auth persistence keys — JWT in localStorage; UI-only keys in sessionStorage. */

export const CNS_ACCESS_TOKEN_KEY = 'cns_access_token';
export const CNS_SELECTED_PROJECT_KEY = 'cns_selected_project_id';

function readSessionToken(): string | null {
  try {
    return sessionStorage.getItem(CNS_ACCESS_TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Read JWT from localStorage (migrates legacy sessionStorage token once). */
export function getStoredAccessToken(): string | null {
  try {
    let token = localStorage.getItem(CNS_ACCESS_TOKEN_KEY);
    if (token) return token;

    const legacy = readSessionToken();
    if (legacy) {
      localStorage.setItem(CNS_ACCESS_TOKEN_KEY, legacy);
      sessionStorage.removeItem(CNS_ACCESS_TOKEN_KEY);
      return legacy;
    }
    return null;
  } catch {
    return readSessionToken();
  }
}

/** Persist JWT in localStorage so sessions survive tab close and browser restart. */
export function setStoredAccessToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(CNS_ACCESS_TOKEN_KEY, token);
      sessionStorage.removeItem(CNS_ACCESS_TOKEN_KEY);
    } else {
      localStorage.removeItem(CNS_ACCESS_TOKEN_KEY);
      sessionStorage.removeItem(CNS_ACCESS_TOKEN_KEY);
    }
  } catch {
    // ignore (private mode, etc.)
  }
}

/** Remove JWT and UI-only session keys. Safe to call multiple times. */
export function clearAuthSessionStorage(): void {
  try {
    localStorage.removeItem(CNS_ACCESS_TOKEN_KEY);
    sessionStorage.removeItem(CNS_ACCESS_TOKEN_KEY);
    sessionStorage.removeItem(CNS_SELECTED_PROJECT_KEY);
  } catch {
    // ignore
  }
}
