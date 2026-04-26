import type { Handler } from "@netlify/functions";

import { createGameSession, getDeckById } from "../../src/lib/server/data";
import {
  isPost,
  jsonResponse,
  notFound,
  parseJsonBody,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
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

    const deck = await getDeckById(request.deckId);
    if (!deck || deck.user_id !== user.id) {
      notFound("Deck not found.");
    }

    const session = await createGameSession({ deckId: request.deckId });

    const response: StartSessionResponse = {
      sessionId: session.id,
      createdAt: session.created_at,
    };

    return jsonResponse(200, response);
  });
