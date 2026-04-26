import type { Handler } from "@netlify/functions";

import { normalizeCardName, parseHandInput, splitCommanders } from "../../src/lib/decklist";
import { ensureCardsCached } from "../../src/lib/server/card-cache";
import { analyzeOpeningHand, alignCardsToInput, buildStoredHandCards } from "../../src/lib/server/hand-analysis";
import {
  createHandSnapshot,
  getDeckById,
  getGameSession,
} from "../../src/lib/server/data";
import {
  badRequest,
  isPost,
  jsonResponse,
  notFound,
  parseJsonBody,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
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

    const user = await requireUser(event);
    const request = parseJsonBody<AnalyzeHandRequest>(event);

    if (!request.sessionId) {
      badRequest("Session ID is required.");
    }

    const handNames = parseHandInput(request.openingHandText);
    if (handNames.length !== 7) {
      badRequest("Opening hand must contain exactly 7 cards.");
    }

    const session = await getGameSession(request.sessionId);
    if (!session) {
      notFound("Game session not found.");
    }

    const deck = await getDeckById(session.deck_id);
    if (!deck || deck.user_id !== user.id) {
      notFound("Game session not found.");
    }

    const commanderNames = splitCommanders(deck.commander);
    const { cards: cachedCards, unresolved } = await ensureCardsCached(
      [...handNames, ...commanderNames],
      {
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

    const snapshot = await createHandSnapshot({
      sessionId: request.sessionId,
      mulligan_number: request.mulliganNumber,
      seat_position: request.seatPosition,
      cards: buildStoredHandCards(openingHandCards),
      decision: result.decision,
      confidence: result.confidence,
      reasoning: result.reasoning,
      turn_plan: result.turn_plan,
    });

    const response: AnalyzeHandResponse = {
      sessionId: request.sessionId,
      snapshotId: snapshot.id,
      result,
    };

    return jsonResponse(200, response);
  });
