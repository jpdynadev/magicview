"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";
import { getSupabaseBrowserClient } from "@/lib/supabase-browser";

export function AuthCard() {
  const router = useRouter();
  const { configError } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    setError(null);

    try {
      const supabase = getSupabaseBrowserClient();

      if (mode === "signup") {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
        });

        if (signUpError) {
          throw signUpError;
        }

        if (data.session) {
          router.replace("/dashboard");
          return;
        }

        setMessage(
          "Account created. If email confirmation is enabled in Supabase, confirm the email and then sign in.",
        );
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });

        if (signInError) {
          throw signInError;
        }

        router.replace("/dashboard");
      }
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

      {configError ? (
        <p className="notice error">
          {configError} Add `NEXT_PUBLIC_SUPABASE_URL` and
          `NEXT_PUBLIC_SUPABASE_ANON_KEY` in Netlify before auth will work.
        </p>
      ) : null}
      {message ? <p className="notice success">{message}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}
    </div>
  );
}
