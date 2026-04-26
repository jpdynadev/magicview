"use client";

import { useState, type FormEvent } from "react";

import { callNetlifyFunction } from "@/lib/api";
import type { UpsertDeckResponse } from "@/lib/types";

interface DeckEditorProps {
  onSaved: (deckId: string) => Promise<void> | void;
}

const DEFAULT_DECKLIST = `1 Sol Ring
1 Arcane Signet
1 Command Tower
1 Cultivate
1 Kodama's Reach
1 Swords to Plowshares
1 Beast Within`;

export function DeckEditor({ onSaved }: DeckEditorProps) {
  const [name, setName] = useState("");
  const [commander, setCommander] = useState("");
  const [bracket, setBracket] = useState(3);
  const [strategySummary, setStrategySummary] = useState("");
  const [decklistText, setDecklistText] = useState(DEFAULT_DECKLIST);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    setError(null);

    try {
      const response = await callNetlifyFunction<UpsertDeckResponse>("upsert-deck", {
        name,
        commander,
        bracket,
        strategySummary,
        decklistText,
      });

      const unresolvedNote = response.unresolvedCards.length
        ? ` Unresolved cards: ${response.unresolvedCards.join(", ")}.`
        : "";

      setMessage(
        `Deck saved with ${response.parsedCards} cards.${unresolvedNote}`,
      );
      await onSaved(response.deckId);
      setName("");
      setCommander("");
      setBracket(3);
      setStrategySummary("");
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Failed to save deck.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel stack gap-md">
      <div className="stack gap-xs">
        <span className="eyebrow">Create deck</span>
        <h2>Paste a decklist and move straight to hands.</h2>
        <p>
          Commanders can be comma-separated for partner decks. Strategy summary is optional;
          MagicView will generate a lean fallback summary from cached card tags.
        </p>
      </div>

      <form className="stack gap-md" onSubmit={handleSubmit}>
        <label className="field">
          <span>Deck name</span>
          <input
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Tivit Turns"
            required
          />
        </label>

        <div className="split-fields">
          <label className="field">
            <span>Commander(s)</span>
            <input
              className="input"
              value={commander}
              onChange={(event) => setCommander(event.target.value)}
              placeholder="Tivit, Seller of Secrets"
              required
            />
          </label>
          <label className="field field-compact">
            <span>Bracket</span>
            <select
              className="input"
              value={bracket}
              onChange={(event) => setBracket(Number(event.target.value))}
            >
              {[1, 2, 3, 4, 5].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="field">
          <span>Strategy summary</span>
          <textarea
            className="textarea"
            rows={4}
            value={strategySummary}
            onChange={(event) => setStrategySummary(event.target.value)}
            placeholder="Esper artifact combo-control deck that ramps, grinds value, and assembles extra turns."
          />
        </label>

        <label className="field">
          <span>Decklist</span>
          <textarea
            className="textarea decklist-textarea"
            rows={14}
            value={decklistText}
            onChange={(event) => setDecklistText(event.target.value)}
            placeholder="1 Sol Ring&#10;1 Arcane Signet&#10;1 Command Tower"
            required
          />
        </label>

        <button className="button" type="submit" disabled={loading}>
          {loading ? "Saving..." : "Save deck"}
        </button>
      </form>

      {message ? <p className="notice success">{message}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}
    </div>
  );
}
