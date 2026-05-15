import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { UserPublic } from '../types/auth';
import { fetchMe, loginUser, logoutApi, registerUser } from '../api/auth';
import { setStoredAccessToken } from '../api/client';

interface AuthState {
  user: UserPublic | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, display_name: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const m = await fetchMe();
      setUser(m.user);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const m = await fetchMe();
        if (!cancelled) setUser(m.user);
      } catch {
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

  const logout = useCallback(async () => {
    try {
      await logoutApi();
    } catch {
      setStoredAccessToken(null);
    }
    await refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ user, loading, refresh, login, register, logout }),
    [user, loading, refresh, login, register, logout],
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
