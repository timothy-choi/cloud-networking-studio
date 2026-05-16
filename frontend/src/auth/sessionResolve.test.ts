import { describe, expect, it, vi } from 'vitest';
import type { MeResponse } from '../api/auth';
import { ApiError } from '../api/client';
import { resolveUserFromSession } from './sessionResolve';

describe('resolveUserFromSession', () => {
  it('does not call fetchMe when there is no token', async () => {
    const fetchMe = vi.fn<[], Promise<MeResponse>>();
    const r = await resolveUserFromSession(() => null, fetchMe);
    expect(fetchMe).not.toHaveBeenCalled();
    expect(r).toEqual({ user: null, clearStorage: false });
  });

  it('returns user when token exists and fetchMe succeeds', async () => {
    const user = { id: '1', email: 'a@b.com', display_name: 'A' };
    const fetchMe = vi.fn().mockResolvedValue({ user } as MeResponse);
    const r = await resolveUserFromSession(() => 'tok', fetchMe);
    expect(fetchMe).toHaveBeenCalledOnce();
    expect(r.user).toEqual(user);
    expect(r.clearStorage).toBe(false);
  });

  it('returns clearStorage on 401', async () => {
    const fetchMe = vi.fn().mockRejectedValue(new ApiError(401, 'Unauthorized', {}));
    const r = await resolveUserFromSession(() => 'bad', fetchMe);
    expect(r.user).toBeNull();
    expect(r.clearStorage).toBe(true);
  });

  it('returns clearStorage if token removed after fetchMe', async () => {
    const state = { token: 'x' as string | null };
    const fetchMe = vi.fn().mockImplementation(async () => {
      state.token = null;
      return { user: { id: '1', email: 'a@b.com', display_name: 'A' } } as MeResponse;
    });
    const r = await resolveUserFromSession(() => state.token, fetchMe);
    expect(r.user).toBeNull();
    expect(r.clearStorage).toBe(true);
  });
});
