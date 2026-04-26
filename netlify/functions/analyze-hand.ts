import type { Handler } from "@netlify/functions";

import { normalizeCardName, parseHandInput, splitCommanders } from "../../src/lib/decklist";
import { ensureCardsCached } from "../../src/lib/server/card-cache";
import { buildStoredHandCards, analyzeOpeningHand, alignCardsToInput } from "../../src/lib/server/hand-analysis";
import {
  isPost,
  jsonResponse,
  parseJsonBody,
  requireUserId,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import { getSupabaseAdminClient } from "../../src/lib/server/supabase-admin";
import type {
  AnalyzeHandRequest,
  AnalyzeHandResponse,
  CachedCard,
  MulliganPromptPayload,
} from "../../src/lib/types";

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const userId = await requireUserId(event);
    const request = parseJsonBody<AnalyzeHandRequest>(event);

    if (!request.sessionId) {
      throw new Error("Session ID is required.");
    }

    const handNames = parseHandInput(request.openingHandText);
    if (handNames.length !== 7) {
      throw new Error("Opening hand must contain exactly 7 cards.");
    }

    const supabase = getSupabaseAdminClient();
    const { data: session, error: sessionError } = await supabase
      .from("game_sessions")
      .select("id,deck_id")
      .eq("id", request.sessionId)
      .single();

    if (sessionError || !session) {
      throw new Error("Game session not found.");
    }

    const { data: deckRow, error: deckError } = await supabase
      .from("decks")
      .select("id,user_id,commander,bracket,strategy_summary")
      .eq("id", session.deck_id)
      .eq("user_id", userId)
      .single();

    if (deckError || !deckRow) {
      throw new Error("Deck not found for this session.");
    }

    const deck = deckRow as {
      id: string;
      user_id: string;
      commander: string;
      bracket: number;
      strategy_summary: string | null;
    };

    const commanderNames = splitCommanders(deck.commander);
    const { cards: cachedCards, unresolved } = await ensureCardsCached(
      [...handNames, ...commanderNames],
      {
        supabase,
        compressWithAi: true,
      },
    );

    if (unresolved.length) {
      throw new Error(`Could not resolve cards: ${unresolved.join(", ")}`);
    }

    const openingHandCards = alignCardsToInput(handNames, cachedCards);
    const commanderCards = commanderNames
      .map((name) => cachedCards.get(normalizeCardName(name)))
      .filter(Boolean) as CachedCard[];

    const commanderSummary = commanderCards.length
      ? commanderCards
          .map((card) => card.compact_summary || `${card.name} has no cached summary yet.`)
          .join(" ")
      : "Commander cache miss.";

    const payload: MulliganPromptPayload = {
      commander: deck.commander,
      bracket: deck.bracket,
      deck_strategy: `${commanderSummary} ${deck.strategy_summary ?? ""}`.trim(),
      opening_hand: buildStoredHandCards(openingHandCards),
      seat_position: request.seatPosition,
      mulligan_number: request.mulliganNumber,
    };

    const result = await analyzeOpeningHand(payload);

    const { data, error } = await supabase
      .from("hand_snapshots")
      .insert({
        session_id: request.sessionId,
        mulligan_number: request.mulliganNumber,
        seat_position: request.seatPosition,
        cards: buildStoredHandCards(openingHandCards),
        decision: result.decision,
        confidence: result.confidence,
        reasoning: result.reasoning,
        turn_plan: result.turn_plan,
      })
      .select("id")
      .single();

    if (error || !data) {
      throw new Error("Failed to save hand snapshot.");
    }

    const response: AnalyzeHandResponse = {
      sessionId: request.sessionId,
      snapshotId: data.id as string,
      result,
    };

    return jsonResponse(200, response);
  });
