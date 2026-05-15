import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { UserPublic } from '../types/auth';
import { fetchMe, loginUser, logoutApi, registerUser } from '../api/auth';
import { ApiError, getStoredAccessToken, setStoredAccessToken } from '../api/client';
import { clearAuthSessionStorage } from './storage';

interface AuthState {
  user: UserPublic | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, display_name: string) => Promise<void>;
  /** Clears token/project storage and user state; does not call the server. */
  clearSession: () => void;
  /** Calls optional POST /auth/logout, clears storage, then sends user to /login. */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

function shouldSkipImplicitMeProbe(): boolean {
  return import.meta.env.VITE_AUTH_SKIP_IMPLICIT_ME === 'true';
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (shouldSkipImplicitMeProbe() && !getStoredAccessToken()) {
      setUser(null);
      return;
    }
    try {
      const m = await fetchMe();
      setUser(m.user);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        clearAuthSessionStorage();
      }
      setUser(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      if (shouldSkipImplicitMeProbe() && !getStoredAccessToken()) {
        if (!cancelled) {
          setUser(null);
          setLoading(false);
        }
        return;
      }
      try {
        const m = await fetchMe();
        if (!cancelled) setUser(m.user);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          clearAuthSessionStorage();
        }
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const t = await loginUser({ email, password });
    setStoredAccessToken(t.access_token);
    setUser(t.user);
  }, []);

  const register = useCallback(async (email: string, password: string, display_name: string) => {
    const t = await registerUser({ email, password, display_name });
    setStoredAccessToken(t.access_token);
    setUser(t.user);
  }, []);

  const clearSession = useCallback(() => {
    clearAuthSessionStorage();
    setUser(null);
    navigate('/login', { replace: true });
  }, [navigate]);

  const logout = useCallback(async () => {
    try {
      await logoutApi();
    } catch {
      clearAuthSessionStorage();
    }
    setUser(null);
    navigate('/login', { replace: true });
  }, [navigate]);

  const value = useMemo(
    () => ({ user, loading, refresh, login, register, clearSession, logout }),
    [user, loading, refresh, login, register, clearSession, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
