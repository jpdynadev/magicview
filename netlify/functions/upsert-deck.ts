import type { Handler } from "@netlify/functions";

import { normalizeCardName, parseDecklist, splitCommanders } from "../../src/lib/decklist";
import { buildDeckStrategySummary } from "../../src/lib/server/deck-strategy";
import { ensureCardsCached } from "../../src/lib/server/card-cache";
import { queryOne, getSql } from "../../src/lib/server/db";
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

    const sql = getSql();
    let deckId = request.deckId;

    if (deckId) {
      const updatedDeck = await queryOne<Record<string, unknown>>(
        `
          update decks
          set
            name = $1,
            commander = $2,
            bracket = $3,
            strategy_summary = $4
          where id = $5 and user_id = $6
          returning id
        `,
        [
          request.name.trim(),
          request.commander.trim(),
          request.bracket,
          strategySummary,
          deckId,
          user.id,
        ],
      );

      if (!updatedDeck) {
        notFound("Deck not found.");
      }

      await sql.query(
        `
          delete from deck_cards
          where deck_id = $1
        `,
        [deckId],
      );
    } else {
      const insertedDeck = await queryOne<Record<string, unknown>>(
        `
          insert into decks (user_id, name, commander, bracket, strategy_summary)
          values ($1, $2, $3, $4, $5)
          returning id
        `,
        [
          user.id,
          request.name.trim(),
          request.commander.trim(),
          request.bracket,
          strategySummary,
        ],
      );

      if (!insertedDeck) {
        throw new Error("Failed to create deck.");
      }

      deckId = String(insertedDeck.id);
    }

    if (!deckId) {
      throw new Error("Deck ID was not resolved.");
    }

    const cardNames = parsedDecklist.map((entry) => {
      const cached = cachedCards.get(normalizeCardName(entry.cardName));
      return cached?.name ?? entry.cardName;
    });
    const quantities = parsedDecklist.map((entry) => entry.quantity);

    if (cardNames.length) {
      await sql.query(
        `
          insert into deck_cards (deck_id, card_name, quantity)
          select
            $1::uuid,
            unnest($2::text[]),
            unnest($3::integer[])
        `,
        [deckId, cardNames, quantities],
      );
    }

    const response: UpsertDeckResponse = {
      deckId,
      strategySummary,
      parsedCards: parsedDecklist.reduce((sum, entry) => sum + entry.quantity, 0),
      unresolvedCards: unresolved,
    };

    return jsonResponse(200, response);
  });

