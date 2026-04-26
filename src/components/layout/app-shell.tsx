"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth-context";
import { getSupabaseBrowserClient } from "@/lib/supabase-browser";

interface AppShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  actions?: ReactNode;
}

export function AppShell({ title, subtitle, children, actions }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useAuth();

  const handleSignOut = async () => {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace("/auth");
  };

  return (
    <main className="app-shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow">Commander AI mulligan coach</span>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        <div className="hero-side">
          <div className="status-chip">
            <span className="status-dot" />
            {user?.email ?? "Guest"}
          </div>
          <div className="nav-links">
            <Link
              className={pathname?.startsWith("/dashboard") ? "nav-link active" : "nav-link"}
              href="/dashboard"
            >
              Dashboard
            </Link>
          </div>
          <div className="hero-actions">
            {actions}
            {user ? (
              <button className="button ghost" type="button" onClick={handleSignOut}>
                Sign out
              </button>
            ) : null}
          </div>
        </div>
      </section>
      <section className="content-grid">{children}</section>
    </main>
  );
}

