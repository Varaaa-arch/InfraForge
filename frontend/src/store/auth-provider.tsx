import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { getCurrentUser, loginRequest, logoutRequest } from "@/api/auth";
import {
  AUTH_LOGOUT_EVENT,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "@/lib/auth-storage";
import { AuthContext, type AuthContextValue } from "@/store/auth-context";
import type { AuthStatus, User } from "@/types/auth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      if (!getAccessToken()) {
        setStatus("unauthenticated");
        return;
      }

      try {
        const currentUser = await getCurrentUser();
        if (!cancelled) {
          setUser(currentUser);
          setStatus("authenticated");
        }
      } catch {
        clearTokens();
        if (!cancelled) {
          setUser(null);
          setStatus("unauthenticated");
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleLogout = () => {
      setUser(null);
      setStatus("unauthenticated");
    };

    window.addEventListener(AUTH_LOGOUT_EVENT, handleLogout);
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, handleLogout);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await loginRequest({ username, password });
    setTokens(tokens);

    try {
      const currentUser = await getCurrentUser();
      setUser(currentUser);
      setStatus("authenticated");
      return currentUser;
    } catch (error) {
      clearTokens();
      setUser(null);
      setStatus("unauthenticated");
      throw error;
    }
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    try {
      if (refreshToken) {
        await logoutRequest(refreshToken);
      }
    } catch {
      // Token mungkin sudah kedaluwarsa — sesi lokal tetap dibersihkan.
    } finally {
      clearTokens();
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, logout }),
    [user, status, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
