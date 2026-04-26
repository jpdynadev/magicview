import type { Handler } from "@netlify/functions";

import { queryMany } from "../../src/lib/server/db";
import {
  isPost,
  jsonResponse,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import { mapDeckRow } from "../../src/lib/server/serializers";
import type { ListDecksResponse } from "../../src/lib/types";

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const user = await requireUser(event);
    const rows = await queryMany<Record<string, unknown>>(
      `
        select id, user_id, name, commander, bracket, strategy_summary, created_at, updated_at
        from decks
        where user_id = $1
        order by created_at desc
      `,
      [user.id],
    );

    const response: ListDecksResponse = {
      decks: rows.map(mapDeckRow),
    };

    return jsonResponse(200, response);
  });

