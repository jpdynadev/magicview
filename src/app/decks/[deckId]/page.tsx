"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { RequireAuth } from "@/components/auth/require-auth";
import { AppShell } from "@/components/layout/app-shell";
import { callNetlifyFunction } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Deck, DeckCard, DeckDetailResponse, GameSession, HandSnapshot } from "@/lib/types";

export default function DeckDetailPage() {
  const params = useParams<{ deckId: string }>();
  const { user } = useAuth();
  const [deck, setDeck] = useState<Deck | null>(null);
  const [cards, setCards] = useState<DeckCard[]>([]);
  const [sessions, setSessions] = useState<GameSession[]>([]);
  const [snapshots, setSnapshots] = useState<HandSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDeck = async () => {
      if (!user || !params.deckId) {
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const response = await callNetlifyFunction<DeckDetailResponse>("get-deck", {
          deckId: params.deckId,
        });

        setDeck(response.deck);
        setCards(response.cards);
        setSessions(response.sessions);
        setSnapshots(response.snapshots);
      } catch (loadError) {
        setError(
          loadError instanceof Error ? loadError.message : "Failed to load deck.",
        );
      } finally {
        setLoading(false);
      }
    };

    void loadDeck();
  }, [params.deckId, user]);

  const totalCards = cards.reduce((sum, card) => sum + card.quantity, 0);

  return (
    <RequireAuth>
      <AppShell
        title={deck?.name ?? "Deck detail"}
        subtitle="Inspect the imported list, check the inferred strategy summary, and jump into a new Commander session."
        actions={
          <Link className="button" href={`/decks/${params.deckId}/start-game`}>
            Start game
          </Link>
        }
      >
        <div className="stack gap-md">
          {error ? <p className="notice error">{error}</p> : null}
          <div className="panel stack gap-md">
            <div className="deck-card-top">
              <div>
                <span className="eyebrow">Deck profile</span>
                <h2>{deck?.commander ?? "Loading..."}</h2>
              </div>
              {deck ? <span className="badge">Bracket {deck.bracket}</span> : null}
            </div>
            <p>
              {loading
                ? "Loading deck summary..."
                : deck?.strategy_summary || "No strategy summary saved yet."}
            </p>
            <div className="tag-grid">
              <div className="subpanel">
                <span className="eyebrow">Cards imported</span>
                <h3>{totalCards}</h3>
              </div>
              <div className="subpanel">
                <span className="eyebrow">Sessions played</span>
                <h3>{sessions.length}</h3>
              </div>
              <div className="subpanel">
                <span className="eyebrow">Hands saved</span>
                <h3>{snapshots.length}</h3>
              </div>
            </div>
          </div>

          <div className="panel stack gap-md">
            <div className="stack gap-xs">
              <span className="eyebrow">Recent hands</span>
              <h2>Mulligan history</h2>
            </div>

            {snapshots.length ? (
              <div className="card-list">
                {snapshots.slice(0, 8).map((snapshot) => (
                  <Link
                    className="deck-card"
                    key={snapshot.id}
                    href={`/sessions/${snapshot.session_id}/result?snapshot=${snapshot.id}`}
                  >
                    <div className="deck-card-top">
                      <strong>{snapshot.decision}</strong>
                      <span className="badge">
                        {Math.round(snapshot.confidence * 100)}%
                      </span>
                    </div>
                    <p className="muted-copy">
                      {snapshot.cards.map((card) => card.name).join(", ")}
                    </p>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <h3>No saved hands yet</h3>
                <p>Run your first opening hand analysis from Start Game.</p>
              </div>
            )}
          </div>
        </div>

        <div className="panel stack gap-md">
          <div className="stack gap-xs">
            <span className="eyebrow">Decklist</span>
            <h2>Imported cards</h2>
          </div>

          {loading ? (
            <p className="muted-copy">Loading card list...</p>
          ) : (
            <div className="card-list">
              {cards.slice(0, 40).map((card) => (
                <div className="deck-card" key={card.id}>
                  <div className="deck-card-top">
                    <strong>{card.card_name}</strong>
                    <span className="badge">x{card.quantity}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </AppShell>
    </RequireAuth>
  );
}
