import type { Handler } from "@netlify/functions";

import { normalizeCardName, parseHandInput, splitCommanders } from "../../src/lib/decklist";
import { ensureCardsCached } from "../../src/lib/server/card-cache";
import { analyzeOpeningHand, alignCardsToInput, buildStoredHandCards } from "../../src/lib/server/hand-analysis";
import { queryOne } from "../../src/lib/server/db";
import {
  badRequest,
  isPost,
  jsonResponse,
  notFound,
  parseJsonBody,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import { mapCachedCardRow } from "../../src/lib/server/serializers";
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

    const sessionRow = await queryOne<Record<string, unknown>>(
      `
        select
          gs.id,
          gs.deck_id,
          d.user_id,
          d.commander,
          d.bracket,
          d.strategy_summary
        from game_sessions gs
        join decks d on d.id = gs.deck_id
        where gs.id = $1 and d.user_id = $2
      `,
      [request.sessionId, user.id],
    );

    if (!sessionRow) {
      notFound("Game session not found.");
    }

    const deck = {
      id: String(sessionRow.deck_id),
      user_id: String(sessionRow.user_id),
      commander: String(sessionRow.commander),
      bracket: Number(sessionRow.bracket),
      strategy_summary:
        sessionRow.strategy_summary == null
          ? null
          : String(sessionRow.strategy_summary),
    };

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

    const snapshotRow = await queryOne<Record<string, unknown>>(
      `
        insert into hand_snapshots (
          session_id,
          mulligan_number,
          seat_position,
          cards,
          decision,
          confidence,
          reasoning,
          turn_plan
        )
        values ($1, $2, $3, $4::jsonb, $5, $6, $7, $8::jsonb)
        returning id
      `,
      [
        request.sessionId,
        request.mulliganNumber,
        request.seatPosition,
        JSON.stringify(buildStoredHandCards(openingHandCards)),
        result.decision,
        result.confidence,
        result.reasoning,
        JSON.stringify(result.turn_plan),
      ],
    );

    if (!snapshotRow) {
      throw new Error("Failed to save hand snapshot.");
    }

    const response: AnalyzeHandResponse = {
      sessionId: request.sessionId,
      snapshotId: String(snapshotRow.id),
      result,
    };

    return jsonResponse(200, response);
  });
