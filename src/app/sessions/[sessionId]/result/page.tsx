"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { RequireAuth } from "@/components/auth/require-auth";
import { AppShell } from "@/components/layout/app-shell";
import { ResultCard } from "@/components/session/result-card";
import { callNetlifyFunction } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Deck, GameSession, HandSnapshot, ResultDetailResponse } from "@/lib/types";

export default function ResultPage() {
  const params = useParams<{ sessionId: string }>();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const snapshotId = searchParams.get("snapshot");
  const [session, setSession] = useState<GameSession | null>(null);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [snapshot, setSnapshot] = useState<HandSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadResult = async () => {
      if (!user || !params.sessionId || !snapshotId) {
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const response = await callNetlifyFunction<ResultDetailResponse>(
          "get-result",
          {
            sessionId: params.sessionId,
            snapshotId,
          },
        );

        setSession(response.session);
        setDeck(response.deck);
        setSnapshot(response.snapshot);
      } catch (loadError) {
        setError(
          loadError instanceof Error ? loadError.message : "Result not found.",
        );
      } finally {
        setLoading(false);
      }
    };

    void loadResult();
  }, [params.sessionId, snapshotId, user]);

  return (
    <RequireAuth>
      <AppShell
        title="Mulligan result"
        subtitle="Structured reasoning, confidence, and a short turn plan based only on the commander, deck summary, and 7 visible cards."
        actions={
          deck ? (
            <Link className="button" href={`/decks/${deck.id}/start-game`}>
              Analyze another hand
            </Link>
          ) : null
        }
      >
        <div className="stack gap-md">
          {error ? <p className="notice error">{error}</p> : null}
          {loading ? (
            <div className="panel">
              <p className="muted-copy">Loading saved result...</p>
            </div>
          ) : snapshot && deck ? (
            <ResultCard
              snapshot={snapshot}
              commander={deck.commander}
              deckName={deck.name}
            />
          ) : (
            <div className="empty-state">
              <h3>No result found</h3>
              <p>Start a session from the deck page and analyze a 7-card hand first.</p>
            </div>
          )}
        </div>

        <div className="panel stack gap-md">
          <div className="stack gap-xs">
            <span className="eyebrow">Session metadata</span>
            <h2>Saved snapshot</h2>
          </div>
          <div className="tag-grid">
            <div className="subpanel">
              <span className="eyebrow">Session ID</span>
              <p>{session?.id ?? "-"}</p>
            </div>
            <div className="subpanel">
              <span className="eyebrow">Snapshot ID</span>
              <p>{snapshot?.id ?? "-"}</p>
            </div>
            <div className="subpanel">
              <span className="eyebrow">Created</span>
              <p>{snapshot?.created_at ? new Date(snapshot.created_at).toLocaleString() : "-"}</p>
            </div>
          </div>
        </div>
      </AppShell>
    </RequireAuth>
  );
}
