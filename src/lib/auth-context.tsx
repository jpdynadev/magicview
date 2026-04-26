"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  clearStoredAuthToken,
  getStoredAuthToken,
  setStoredAuthToken,
} from "@/lib/auth-storage";
import { callNetlifyFunction } from "@/lib/api";
import type { AppUser, AuthResponse, MeResponse } from "@/lib/types";

interface AuthContextValue {
  loading: boolean;
  token: string | null;
  user: AppUser | null;
  signIn: (auth: AuthResponse) => void;
  signOut: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  loading: true,
  token: null,
  user: null,
  signIn: () => undefined,
  signOut: () => undefined,
  refreshUser: async () => undefined,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AppUser | null>(null);

  const signOut = () => {
    clearStoredAuthToken();
    setToken(null);
    setUser(null);
  };

  const signIn = (auth: AuthResponse) => {
    setStoredAuthToken(auth.token);
    setToken(auth.token);
    setUser(auth.user);
  };

  const refreshUser = async () => {
    const currentToken = getStoredAuthToken();

    if (!currentToken) {
      setToken(null);
      setUser(null);
      setLoading(false);
      return;
    }

    setToken(currentToken);

    try {
      const response = await callNetlifyFunction<MeResponse>(
        "me",
        {},
        {
          token: currentToken,
        },
      );
      setUser(response.user);
    } catch {
      signOut();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshUser();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        loading,
        token,
        user,
        signIn,
        signOut,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
