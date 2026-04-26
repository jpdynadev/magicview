import type { Handler } from "@netlify/functions";

import {
  getDeckById,
  getDeckCards,
  listGameSessionsForDeck,
  listHandSnapshotsForDeck,
} from "../../src/lib/server/data";
import {
  isPost,
  jsonResponse,
  notFound,
  parseJsonBody,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import { requireUuid } from "../../src/lib/server/validators";
import type { DeckDetailResponse } from "../../src/lib/types";

interface GetDeckRequest {
  deckId: string;
}

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const user = await requireUser(event);
    const request = parseJsonBody<GetDeckRequest>(event);
    const deckId = requireUuid(request.deckId, "Deck ID");

    const deck = await getDeckById(deckId);
    if (!deck || deck.user_id !== user.id) {
      notFound("Deck not found.");
    }

    const [cards, sessions, snapshots] = await Promise.all([
      getDeckCards(deckId).then((items) =>
        items.sort((a, b) => (a.card_name > b.card_name ? 1 : -1)),
      ),
      listGameSessionsForDeck(deckId),
      listHandSnapshotsForDeck(deckId),
    ]);

    const response: DeckDetailResponse = {
      deck,
      cards,
      sessions,
      snapshots,
    };

    return jsonResponse(200, response);
  });
