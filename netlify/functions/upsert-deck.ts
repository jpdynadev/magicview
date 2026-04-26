import type { Handler } from "@netlify/functions";

import { normalizeCardName, parseDecklist, splitCommanders } from "../../src/lib/decklist";
import { buildDeckStrategySummary } from "../../src/lib/server/deck-strategy";
import { ensureCardsCached } from "../../src/lib/server/card-cache";
import {
  getDeckById,
  replaceDeckCards,
  upsertDeck,
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
import type { CachedCard, UpsertDeckRequest, UpsertDeckResponse } from "../../src/lib/types";

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const user = await requireUser(event);
    const request = parseJsonBody<UpsertDeckRequest>(event);

    if (!request.name?.trim()) {
      badRequest("Deck name is required.");
    }

    if (!request.commander?.trim()) {
      badRequest("Commander field is required.");
    }

    if (!request.decklistText?.trim()) {
      badRequest("Decklist is required.");
    }

    if (request.bracket < 1 || request.bracket > 5) {
      badRequest("Bracket must be between 1 and 5.");
    }

    const parsedDecklist = parseDecklist(request.decklistText);
    const commanderNames = splitCommanders(request.commander);
    const allLookupNames = [
      ...commanderNames,
      ...parsedDecklist.map((entry) => entry.cardName),
    ];

    const { cards: cachedCards, unresolved } = await ensureCardsCached(
      allLookupNames,
      {
        compressWithAi: true,
      },
    );

    const commanderCards = commanderNames
      .map((name) => cachedCards.get(normalizeCardName(name)))
      .filter(Boolean) as CachedCard[];

    const deckCardsForSummary = parsedDecklist
      .map((entry) => cachedCards.get(normalizeCardName(entry.cardName)))
      .filter(Boolean) as CachedCard[];

    const strategySummary = buildDeckStrategySummary({
      commanders: commanderCards,
      deckCards: deckCardsForSummary,
      existingSummary: request.strategySummary,
    });

    let deckId = request.deckId;

    if (deckId) {
      const existing = await getDeckById(deckId);
      if (!existing || existing.user_id !== user.id) {
        notFound("Deck not found.");
      }
    }

    const deck = await upsertDeck({
      deckId,
      userId: user.id,
      name: request.name.trim(),
      commander: request.commander.trim(),
      bracket: request.bracket,
      strategy_summary: strategySummary,
    });

    deckId = deck.id;

    const cardNames = parsedDecklist.map((entry) => {
      const cached = cachedCards.get(normalizeCardName(entry.cardName));
      return cached?.name ?? entry.cardName;
    });
    const quantities = parsedDecklist.map((entry) => entry.quantity);

    await replaceDeckCards({
      deckId,
      cards: cardNames.map((name, index) => ({
        card_name: name,
        quantity: quantities[index] ?? 1,
      })),
    });

    const response: UpsertDeckResponse = {
      deckId,
      strategySummary,
      parsedCards: parsedDecklist.reduce((sum, entry) => sum + entry.quantity, 0),
      unresolvedCards: unresolved,
    };

    return jsonResponse(200, response);
  });
