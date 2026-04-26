import type { Handler } from "@netlify/functions";

import { queryOne } from "../../src/lib/server/db";
import {
  isPost,
  jsonResponse,
  notFound,
  parseJsonBody,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import {
  mapDeckRow,
  mapGameSessionRow,
  mapHandSnapshotRow,
} from "../../src/lib/server/serializers";
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

    const sessionRow = await queryOne<Record<string, unknown>>(
      `
        select gs.id, gs.deck_id, gs.created_at
        from game_sessions gs
        join decks d on d.id = gs.deck_id
        where gs.id = $1 and d.user_id = $2
      `,
      [sessionId, user.id],
    );

    if (!sessionRow) {
      notFound("Session not found.");
    }

    const deckRow = await queryOne<Record<string, unknown>>(
      `
        select id, user_id, name, commander, bracket, strategy_summary, created_at, updated_at
        from decks
        where id = $1 and user_id = $2
      `,
      [sessionRow.deck_id, user.id],
    );

    const snapshotRow = await queryOne<Record<string, unknown>>(
      `
        select id, session_id, mulligan_number, seat_position, cards, decision, confidence, reasoning, turn_plan, created_at
        from hand_snapshots
        where id = $1 and session_id = $2
      `,
      [snapshotId, sessionId],
    );

    if (!deckRow || !snapshotRow) {
      notFound("Result not found.");
    }

    const response: ResultDetailResponse = {
      session: mapGameSessionRow(sessionRow),
      deck: mapDeckRow(deckRow),
      snapshot: mapHandSnapshotRow(snapshotRow),
    };

    return jsonResponse(200, response);
  });

