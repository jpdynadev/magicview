import type { HandlerEvent, HandlerResponse } from "@netlify/functions";

import { getSupabaseAdminClient } from "@/lib/server/supabase-admin";

export function jsonResponse(
  statusCode: number,
  body: unknown,
): HandlerResponse {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
    body: JSON.stringify(body),
  };
}

export function parseJsonBody<T>(event: HandlerEvent): T {
  if (!event.body) {
    throw new Error("Request body is required.");
  }

  return JSON.parse(event.body) as T;
}

export async function requireUserId(event: HandlerEvent): Promise<string> {
  const authorization =
    event.headers.authorization ?? event.headers.Authorization;

  if (!authorization?.startsWith("Bearer ")) {
    throw new Error("Missing bearer token.");
  }

  const token = authorization.replace("Bearer ", "");
  const supabase = getSupabaseAdminClient();
  const { data, error } = await supabase.auth.getUser(token);

  if (error || !data.user) {
    throw new Error("Invalid auth token.");
  }

  return data.user.id;
}

export function isPost(event: HandlerEvent): boolean {
  return event.httpMethod.toUpperCase() === "POST";
}

export async function withErrorBoundary(
  callback: () => Promise<HandlerResponse>,
): Promise<HandlerResponse> {
  try {
    return await callback();
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unexpected server error.";
    const statusCode =
      /missing|invalid|required|must/i.test(message) ? 400 : 500;

    return jsonResponse(statusCode, {
      error: message,
    });
  }
}
