"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";

export function RequireAuth({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { loading, user } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/auth");
    }
  }, [loading, router, user]);

  if (loading || !user) {
    return (
      <main className="auth-screen">
        <div className="auth-card">
          <span className="eyebrow">MagicView</span>
          <h1>Checking your session</h1>
          <p>Loading your decks and saved hand history.</p>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}

