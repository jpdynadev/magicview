import type { Handler } from "@netlify/functions";

import {
  isPost,
  jsonResponse,
  parseJsonBody,
  requireUserId,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import { getSupabaseAdminClient } from "../../src/lib/server/supabase-admin";
import type { StartSessionRequest, StartSessionResponse } from "../../src/lib/types";

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const userId = await requireUserId(event);
    const request = parseJsonBody<StartSessionRequest>(event);

    if (!request.deckId) {
      throw new Error("Deck ID is required.");
    }

    const supabase = getSupabaseAdminClient();
    const { data: deck, error: deckError } = await supabase
      .from("decks")
      .select("id")
      .eq("id", request.deckId)
      .eq("user_id", userId)
      .single();

    if (deckError || !deck) {
      throw new Error("Deck not found.");
    }

    const { data, error } = await supabase
      .from("game_sessions")
      .insert({
        deck_id: request.deckId,
      })
      .select("id,created_at")
      .single();

    if (error || !data) {
      throw new Error("Failed to create game session.");
    }

    const response: StartSessionResponse = {
      sessionId: data.id as string,
      createdAt: data.created_at as string,
    };

    return jsonResponse(200, response);
  });

