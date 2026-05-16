import type { MeResponse } from '../api/auth';
import { ApiError } from '../api/client';
import type { UserPublic } from '../types/auth';

export interface SessionResolveResult {
  user: UserPublic | null;
  /** When true, caller should clear JWT + UI session keys (e.g. invalid or stale token). */
  clearStorage: boolean;
}

/**
 * Load the signed-in user only when a token exists.
 * Never calls ``fetchMe`` without a token (avoids treating implicit backend dev user as logged in).
 */
export async function resolveUserFromSession(
  getToken: () => string | null,
  fetchMeFn: () => Promise<MeResponse>,
): Promise<SessionResolveResult> {
  if (!getToken()) {
    return { user: null, clearStorage: false };
  }
  try {
    const m = await fetchMeFn();
    if (!getToken()) {
      return { user: null, clearStorage: true };
    }
    return { user: m.user, clearStorage: false };
  } catch (e) {
    const clearStorage = e instanceof ApiError && e.status === 401;
    return { user: null, clearStorage };
  }
}
