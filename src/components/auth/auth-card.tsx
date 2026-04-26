"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { callPublicNetlifyFunction } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { AuthResponse } from "@/lib/types";

export function AuthCard() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const functionName = mode === "signup" ? "auth-register" : "auth-login";
      const response = await callPublicNetlifyFunction<AuthResponse>(functionName, {
        email,
        password,
      });

      signIn(response);
      router.replace("/dashboard");
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Authentication failed.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-card">
      <div className="stack gap-sm">
        <span className="eyebrow">MagicView MVP</span>
        <h1>Commander mulligans, grounded in your deck.</h1>
        <p>
          Sign in, import a deck, start a game session, and save opening-hand
          decisions with turn plans.
        </p>
      </div>

      <div className="tab-row">
        <button
          className={mode === "signup" ? "button" : "button ghost"}
          type="button"
          onClick={() => setMode("signup")}
        >
          Create account
        </button>
        <button
          className={mode === "signin" ? "button" : "button ghost"}
          type="button"
          onClick={() => setMode("signin")}
        >
          Sign in
        </button>
      </div>

      <form className="stack gap-md" onSubmit={handleSubmit}>
        <label className="field">
          <span>Email</span>
          <input
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@playgroup.gg"
            required
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            className="input"
            type="password"
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="8+ characters"
            minLength={8}
            required
          />
        </label>

        <button className="button" type="submit" disabled={loading}>
          {loading ? "Working..." : mode === "signup" ? "Create account" : "Sign in"}
        </button>
      </form>

      <p className="muted-copy">
        This deployment uses Netlify Functions plus Neon-backed Postgres auth.
      </p>
      {error ? <p className="notice error">{error}</p> : null}
    </div>
  );
}
