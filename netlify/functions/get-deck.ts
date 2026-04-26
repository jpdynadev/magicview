import type { Handler } from "@netlify/functions";

import { queryMany, queryOne } from "../../src/lib/server/db";
import {
  isPost,
  jsonResponse,
  notFound,
  parseJsonBody,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import {
  mapDeckCardRow,
  mapDeckRow,
  mapGameSessionRow,
  mapHandSnapshotRow,
} from "../../src/lib/server/serializers";
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

    const deckRow = await queryOne<Record<string, unknown>>(
      `
        select id, user_id, name, commander, bracket, strategy_summary, created_at, updated_at
        from decks
        where id = $1 and user_id = $2
      `,
      [deckId, user.id],
    );

    if (!deckRow) {
      notFound("Deck not found.");
    }

    const [cardRows, sessionRows, snapshotRows] = await Promise.all([
      queryMany<Record<string, unknown>>(
        `
          select id, deck_id, card_name, quantity
          from deck_cards
          where deck_id = $1
          order by card_name asc
        `,
        [deckId],
      ),
      queryMany<Record<string, unknown>>(
        `
          select id, deck_id, created_at
          from game_sessions
          where deck_id = $1
          order by created_at desc
        `,
        [deckId],
      ),
      queryMany<Record<string, unknown>>(
        `
          select hs.id, hs.session_id, hs.mulligan_number, hs.seat_position, hs.cards, hs.decision, hs.confidence, hs.reasoning, hs.turn_plan, hs.created_at
          from hand_snapshots hs
          join game_sessions gs on gs.id = hs.session_id
          where gs.deck_id = $1
          order by hs.created_at desc
        `,
        [deckId],
      ),
    ]);

    const response: DeckDetailResponse = {
      deck: mapDeckRow(deckRow),
      cards: cardRows.map(mapDeckCardRow),
      sessions: sessionRows.map(mapGameSessionRow),
      snapshots: snapshotRows.map(mapHandSnapshotRow),
    };

    return jsonResponse(200, response);
  });

