import type { Handler } from "@netlify/functions";

import { splitCommanders, normalizeCardName, parseDecklist } from "../../src/lib/decklist";
import { buildDeckStrategySummary } from "../../src/lib/server/deck-strategy";
import {
  isPost,
  jsonResponse,
  parseJsonBody,
  requireUserId,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import { ensureCardsCached } from "../../src/lib/server/card-cache";
import { getSupabaseAdminClient } from "../../src/lib/server/supabase-admin";
import type { CachedCard, UpsertDeckRequest, UpsertDeckResponse } from "../../src/lib/types";

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const userId = await requireUserId(event);
    const request = parseJsonBody<UpsertDeckRequest>(event);

    if (!request.name?.trim()) {
      throw new Error("Deck name is required.");
    }

    if (!request.commander?.trim()) {
      throw new Error("Commander field is required.");
    }

    if (!request.decklistText?.trim()) {
      throw new Error("Decklist is required.");
    }

    if (request.bracket < 1 || request.bracket > 5) {
      throw new Error("Bracket must be between 1 and 5.");
    }

    const supabase = getSupabaseAdminClient();
    const parsedDecklist = parseDecklist(request.decklistText);
    const commanderNames = splitCommanders(request.commander);
    const allLookupNames = [
      ...commanderNames,
      ...parsedDecklist.map((entry) => entry.cardName),
    ];

    const { cards: cachedCards, unresolved } = await ensureCardsCached(
      allLookupNames,
      {
        supabase,
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
      const { error: updateError } = await supabase
        .from("decks")
        .update({
          name: request.name.trim(),
          commander: request.commander.trim(),
          bracket: request.bracket,
          strategy_summary: strategySummary,
        })
        .eq("id", deckId)
        .eq("user_id", userId);

      if (updateError) {
        throw new Error("Failed to update deck.");
      }

      const { error: deleteError } = await supabase
        .from("deck_cards")
        .delete()
        .eq("deck_id", deckId);

      if (deleteError) {
        throw new Error("Failed to refresh deck cards.");
      }
    } else {
      const { data, error: insertError } = await supabase
        .from("decks")
        .insert({
          user_id: userId,
          name: request.name.trim(),
          commander: request.commander.trim(),
          bracket: request.bracket,
          strategy_summary: strategySummary,
        })
        .select("id")
        .single();

      if (insertError || !data) {
        throw new Error("Failed to create deck.");
      }

      deckId = data.id as string;
    }

    const deckCardRows = parsedDecklist.map((entry) => {
      const cached = cachedCards.get(normalizeCardName(entry.cardName));
      return {
        deck_id: deckId,
        card_name: cached?.name ?? entry.cardName,
        quantity: entry.quantity,
      };
    });

    const { error: cardsInsertError } = await supabase
      .from("deck_cards")
      .insert(deckCardRows);

    if (cardsInsertError) {
      throw new Error("Failed to save deck cards.");
    }

    const response: UpsertDeckResponse = {
      deckId,
      strategySummary,
      parsedCards: parsedDecklist.reduce((sum, entry) => sum + entry.quantity, 0),
      unresolvedCards: unresolved,
    };

    return jsonResponse(200, response);
  });

