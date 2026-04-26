import type { Handler } from "@netlify/functions";

import {
  getDeckById,
  getGameSession,
  getHandSnapshot,
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
import type { ResultDetailResponse } from "../../src/lib/types";

interface GetResultRequest {
  sessionId: string;
  snapshotId: string;
}

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const user = await requireUser(event);
    const request = parseJsonBody<GetResultRequest>(event);
    const sessionId = requireUuid(request.sessionId, "Session ID");
    const snapshotId = requireUuid(request.snapshotId, "Snapshot ID");

    const session = await getGameSession(sessionId);
    if (!session) {
      notFound("Session not found.");
    }

    const deck = await getDeckById(session.deck_id);
    const snapshot = await getHandSnapshot(snapshotId);

    if (!deck || deck.user_id !== user.id) {
      notFound("Result not found.");
    }

    if (!snapshot || snapshot.session_id !== sessionId) {
      notFound("Result not found.");
    }

    const response: ResultDetailResponse = {
      session,
      deck,
      snapshot,
    };

    return jsonResponse(200, response);
  });
