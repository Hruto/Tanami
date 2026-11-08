import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, apiGet, apiSend, currentRefreshToken, hasSession, setSession } from "../api/client";
import type { Me, TokenPair } from "../api/types";
import { isStaff } from "../lib/access";

interface AuthState {
  user: Me | null;
  ready: boolean;
  signIn: (identifier: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!hasSession()) {
      setReady(true);
      return;
    }
    apiGet<Me>("/users/me")
      .then((me) => {
        if (cancelled) return;
        if (isStaff(me.role)) setUser(me);
        else setSession(null);
      })
      .catch(() => setSession(null))
      .finally(() => !cancelled && setReady(true));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onSignedOut = () => setUser(null);
    window.addEventListener("tanami:signed-out", onSignedOut);
    return () => window.removeEventListener("tanami:signed-out", onSignedOut);
  }, []);

  const signIn = useCallback(async (identifier: string, password: string) => {
    const trimmed = identifier.trim();
    const credentials = trimmed.includes("@")
      ? { email: trimmed, password }
      : { username: trimmed, password };
    const tokens = await apiSend<TokenPair>("POST", "/auth/login", credentials, false);
    setSession(tokens);
    const me = await apiGet<Me>("/users/me");
    if (!isStaff(me.role)) {
      await apiSend("POST", "/auth/logout", { refresh_token: tokens.refresh_token }, false).catch(() => undefined);
      setSession(null);
      throw new ApiError(
        403,
        "forbidden",
        "Akun ini terdaftar sebagai petani. Ruang kerja ini hanya untuk ahli, moderator, dan admin Tanami.",
        null,
      );
    }
    setUser(me);
  }, []);

  const signOut = useCallback(async () => {
    const refresh = currentRefreshToken();
    if (refresh) {
      await apiSend("POST", "/auth/logout", { refresh_token: refresh }, false).catch(() => undefined);
    }
    setSession(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, ready, signIn, signOut }), [user, ready, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function useMe(): Me {
  const { user } = useAuth();
  if (!user) throw new Error("useMe needs a signed-in user");
  return user;
}
