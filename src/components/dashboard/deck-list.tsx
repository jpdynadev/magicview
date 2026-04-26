"use client";

import Link from "next/link";

import type { Deck } from "@/lib/types";

interface DeckListProps {
  decks: Deck[];
  loading: boolean;
}

export function DeckList({ decks, loading }: DeckListProps) {
  return (
    <div className="panel stack gap-md">
      <div className="stack gap-xs">
        <span className="eyebrow">Your decks</span>
        <h2>Saved Commander builds</h2>
        <p>Every deck keeps its own session history and mulligan snapshots.</p>
      </div>

      {loading ? (
        <p className="muted-copy">Loading decks...</p>
      ) : decks.length ? (
        <div className="card-list">
          {decks.map((deck) => (
            <Link className="deck-card" key={deck.id} href={`/decks/${deck.id}`}>
              <div className="deck-card-top">
                <div>
                  <h3>{deck.name}</h3>
                  <p>{deck.commander}</p>
                </div>
                <span className="badge">Bracket {deck.bracket}</span>
              </div>
              <p className="muted-copy">
                {deck.strategy_summary || "Strategy summary will be inferred from card tags."}
              </p>
            </Link>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <h3>No decks yet</h3>
          <p>Paste your first list on the left to create a playable MVP deck profile.</p>
        </div>
      )}
    </div>
  );
}

