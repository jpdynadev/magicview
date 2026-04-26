"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";

export default function HomePage() {
  const router = useRouter();
  const { loading, user } = useAuth();

  useEffect(() => {
    if (!loading) {
      router.replace(user ? "/dashboard" : "/auth");
    }
  }, [loading, router, user]);

  return (
    <main className="auth-screen">
      <div className="auth-card">
        <span className="eyebrow">MagicView</span>
        <h1>Preparing your Commander workspace.</h1>
        <p>Routing you to auth or your dashboard.</p>
      </div>
    </main>
  );
}

