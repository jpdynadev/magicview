import type { Handler } from "@netlify/functions";

import { listDecksByUser } from "../../src/lib/server/data";
import {
  isPost,
  jsonResponse,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import type { ListDecksResponse } from "../../src/lib/types";

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const user = await requireUser(event);
    const decks = await listDecksByUser(user.id);

    const response: ListDecksResponse = {
      decks,
    };

    return jsonResponse(200, response);
  });
