"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { RequireAuth } from "@/components/auth/require-auth";
import { AppShell } from "@/components/layout/app-shell";
import { callNetlifyFunction } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type {
  AnalyzeHandResponse,
  Deck,
  DeckDetailResponse,
  SeatPosition,
  StartSessionResponse,
} from "@/lib/types";

const SAMPLE_HAND = `Command Tower
Island
Sol Ring
Arcane Signet
Rhystic Study
Swords to Plowshares
Smothering Tithe`;

export default function StartGamePage() {
  const params = useParams<{ deckId: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const [deck, setDeck] = useState<Deck | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [openingHandText, setOpeningHandText] = useState(SAMPLE_HAND);
  const [mulliganNumber, setMulliganNumber] = useState(0);
  const [seatPosition, setSeatPosition] = useState<SeatPosition>("first");
  const [loadingDeck, setLoadingDeck] = useState(true);
  const [creatingSession, setCreatingSession] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDeck = async () => {
      if (!user || !params.deckId) {
        return;
      }

      setLoadingDeck(true);
      setError(null);

      try {
        const response = await callNetlifyFunction<DeckDetailResponse>("get-deck", {
          deckId: params.deckId,
        });
        setDeck(response.deck);
      } catch (loadError) {
        setError(
          loadError instanceof Error ? loadError.message : "Failed to load deck.",
        );
      } finally {
        setLoadingDeck(false);
      }
    };

    void loadDeck();
  }, [params.deckId, user]);

  const handleCreateSession = async () => {
    setCreatingSession(true);
    setError(null);

    try {
      const response = await callNetlifyFunction<StartSessionResponse>("start-session", {
        deckId: params.deckId,
      });
      setSessionId(response.sessionId);
    } catch (sessionError) {
      setError(
        sessionError instanceof Error
          ? sessionError.message
          : "Failed to create session.",
      );
    } finally {
      setCreatingSession(false);
    }
  };

  const handleAnalyze = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!sessionId) {
      setError("Start a game session before analyzing a hand.");
      return;
    }

    setAnalyzing(true);
    setError(null);

    try {
      const response = await callNetlifyFunction<AnalyzeHandResponse>("analyze-hand", {
        sessionId,
        openingHandText,
        mulliganNumber,
        seatPosition,
      });

      router.push(
        `/sessions/${response.sessionId}/result?snapshot=${response.snapshotId}`,
      );
    } catch (analysisError) {
      setError(
        analysisError instanceof Error
          ? analysisError.message
          : "Failed to analyze opening hand.",
      );
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <RequireAuth>
      <AppShell
        title="Start a Commander session"
        subtitle="Create a game session, paste the opening seven, and let the backend return a structured keep-or-mulligan call."
        actions={
          <Link className="button ghost" href={`/decks/${params.deckId}`}>
            Back to deck
          </Link>
        }
      >
        <div className="panel stack gap-md">
          <div className="stack gap-xs">
            <span className="eyebrow">Deck loaded</span>
            <h2>{deck?.name ?? "Loading deck..."}</h2>
            <p>
              {loadingDeck
                ? "Loading deck profile..."
                : `${deck?.commander ?? "Commander"} | Bracket ${deck?.bracket ?? "-"}`}
            </p>
          </div>

          <button
            className="button"
            type="button"
            onClick={handleCreateSession}
            disabled={creatingSession || !!sessionId}
          >
            {creatingSession
              ? "Creating session..."
              : sessionId
                ? "Session active"
                : "Begin new game session"}
          </button>

          {sessionId ? (
            <p className="notice success">Session created: {sessionId}</p>
          ) : null}
          {error ? <p className="notice error">{error}</p> : null}
        </div>

        <div className="panel stack gap-md">
          <div className="stack gap-xs">
            <span className="eyebrow">Opening hand</span>
            <h2>Paste exactly 7 cards</h2>
            <p>
              One per line or comma-separated. The server caches missing cards from
              Scryfall before calling OpenAI.
            </p>
          </div>

          <form className="stack gap-md" onSubmit={handleAnalyze}>
            <div className="split-fields">
              <label className="field field-compact">
                <span>Mulligan number</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={mulliganNumber}
                  onChange={(event) => setMulliganNumber(Number(event.target.value))}
                />
              </label>
              <label className="field field-compact">
                <span>Seat position</span>
                <select
                  className="input"
                  value={seatPosition}
                  onChange={(event) => setSeatPosition(event.target.value as SeatPosition)}
                >
                  <option value="first">First</option>
                  <option value="middle">Middle</option>
                  <option value="last">Last</option>
                </select>
              </label>
            </div>

            <label className="field">
              <span>Opening hand</span>
              <textarea
                className="textarea decklist-textarea"
                rows={12}
                value={openingHandText}
                onChange={(event) => setOpeningHandText(event.target.value)}
                required
              />
            </label>

            <button className="button" type="submit" disabled={analyzing || !sessionId}>
              {analyzing ? "Analyzing..." : "Analyze opening hand"}
            </button>
          </form>
        </div>
      </AppShell>
    </RequireAuth>
  );
}
