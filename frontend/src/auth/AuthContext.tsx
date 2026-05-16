import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { UserPublic } from '../types/auth';
import { fetchMe, loginUser, logoutApi, registerUser } from '../api/auth';
import { getStoredAccessToken, setStoredAccessToken } from '../api/client';
import { clearAuthSessionStorage } from './storage';
import { resolveUserFromSession } from './sessionResolve';

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const { user: u, clearStorage } = await resolveUserFromSession(getStoredAccessToken, fetchMe);
    if (clearStorage) {
      clearAuthSessionStorage();
    }
    setUser(u);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const { user: u, clearStorage } = await resolveUserFromSession(getStoredAccessToken, fetchMe);
      if (clearStorage) {
        clearAuthSessionStorage();
      }
      if (!cancelled) {
        setUser(u);
        setLoading(false);
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
