"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken, User } from "./api";

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string, fullName: string, phone?: string) => Promise<User>;
  loginWithGoogle: (code: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const u = await api<User>("/auth/me");
      setUser(u);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      json: { email, password },
    });
    setToken(res.access_token);
    const u = await api<User>("/auth/me");
    setUser(u);
    return u;
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string, phone?: string) => {
      const res = await api<{ access_token: string }>("/auth/register", {
        method: "POST",
        json: { email, password, full_name: fullName || undefined, phone: phone || undefined },
      });
      setToken(res.access_token);
      const u = await api<User>("/auth/me");
      setUser(u);
      return u;
    },
    []
  );

  const loginWithGoogle = useCallback(async (code: string) => {
    const res = await api<{ access_token: string }>("/auth/google", {
      method: "POST",
      json: { code },
    });
    setToken(res.access_token);
    const u = await api<User>("/auth/me");
    setUser(u);
    return u;
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    location.href = "/login";
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, loginWithGoogle, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
