import type { Handler } from "@netlify/functions";

import {
  isPost,
  jsonResponse,
  notFound,
  parseJsonBody,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import { queryOne } from "../../src/lib/server/db";
import type { StartSessionRequest, StartSessionResponse } from "../../src/lib/types";

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const user = await requireUser(event);
    const request = parseJsonBody<StartSessionRequest>(event);

    if (!request.deckId) {
      throw new Error("Deck ID is required.");
    }

    const deckRow = await queryOne<Record<string, unknown>>(
      `
        select id
        from decks
        where id = $1 and user_id = $2
      `,
      [request.deckId, user.id],
    );

    if (!deckRow) {
      notFound("Deck not found.");
    }

    const sessionRow = await queryOne<Record<string, unknown>>(
      `
        insert into game_sessions (deck_id)
        values ($1)
        returning id, created_at
      `,
      [request.deckId],
    );

    if (!sessionRow) {
      throw new Error("Failed to create game session.");
    }

    const response: StartSessionResponse = {
      sessionId: String(sessionRow.id),
      createdAt: String(sessionRow.created_at),
    };

    return jsonResponse(200, response);
  });
