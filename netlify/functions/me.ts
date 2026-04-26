import type { Handler } from "@netlify/functions";

import {
  isPost,
  jsonResponse,
  requireUser,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import type { MeResponse } from "../../src/lib/types";

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const user = await requireUser(event);
    const response: MeResponse = { user };

    return jsonResponse(200, response);
  });

