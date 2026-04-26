"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth/require-auth";
import { DeckList } from "@/components/dashboard/deck-list";
import { DeckEditor } from "@/components/decks/deck-editor";
import { AppShell } from "@/components/layout/app-shell";
import { useAuth } from "@/lib/auth-context";
import { getSupabaseBrowserClient } from "@/lib/supabase-browser";
import type { Deck } from "@/lib/types";

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [decks, setDecks] = useState<Deck[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDecks = async () => {
    if (!user) {
      return;
    }

    setLoading(true);
    setError(null);

    const supabase = getSupabaseBrowserClient();
    const { data, error: queryError } = await supabase
      .from("decks")
      .select("*")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false });

    if (queryError) {
      setError(queryError.message);
    } else {
      setDecks((data ?? []) as Deck[]);
    }

    setLoading(false);
  };

  useEffect(() => {
    void loadDecks();
  }, [user]);

  return (
    <RequireAuth>
      <AppShell
        title="See the keep before you keep it."
        subtitle="MagicView stores your Commander decks, scores your opening hands, and saves every mulligan decision with real reasoning."
      >
        <DeckEditor
          onSaved={async (deckId) => {
            await loadDecks();
            router.push(`/decks/${deckId}`);
          }}
        />
        <div className="stack gap-md">
          {error ? <p className="notice error">{error}</p> : null}
          <DeckList decks={decks} loading={loading} />
        </div>
      </AppShell>
    </RequireAuth>
  );
}

