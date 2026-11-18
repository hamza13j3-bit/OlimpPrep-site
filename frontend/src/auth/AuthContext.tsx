import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, fetchMe, getToken, login as apiLogin, register as apiRegister, setToken, updateMe } from "../api/client";
import type { Lang, User } from "../api/types";
import { isLanguage, setLanguage } from "../i18n";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (body: { email: string; password: string; name: string; school_group: string; language: Lang }) => Promise<void>;
  logout: () => void;
  updateProfile: (body: Partial<Pick<User, "name" | "school_group" | "language">>) => Promise<User>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => getToken() !== null);

  useEffect(() => {
    if (!getToken()) return;
    fetchMe()
      .then((u) => {
        setUser(u);
        if (isLanguage(u.language)) setLanguage(u.language);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 401) setToken(null); // expired or invalid token
      })
      .finally(() => setLoading(false));
  }, []);

  const adopt = useCallback((u: User, token: string) => {
    setToken(token);
    setUser(u);
    if (isLanguage(u.language)) setLanguage(u.language);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login: async (email, password) => {
        const out = await apiLogin(email, password);
        adopt(out.user, out.access_token);
      },
      register: async (body) => {
        const out = await apiRegister(body);
        adopt(out.user, out.access_token);
      },
      logout: () => {
        setToken(null);
        setUser(null);
      },
      updateProfile: async (body) => {
        const u = await updateMe(body);
        setUser(u);
        return u;
      },
    }),
    [user, loading, adopt],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
