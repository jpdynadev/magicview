import type { HandlerEvent, HandlerResponse } from "@netlify/functions";

import { getSession, getUserById } from "@/lib/server/data";
import type { AppUser } from "@/lib/types";

export class HttpError extends Error {
  statusCode: number;

  constructor(statusCode: number, message: string) {
    super(message);
    this.statusCode = statusCode;
  }
}

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
    throw badRequest("Request body is required.");
  }

  return JSON.parse(event.body) as T;
}

export function badRequest(message: string): never {
  throw new HttpError(400, message);
}

export function unauthorized(message: string): never {
  throw new HttpError(401, message);
}

export function notFound(message: string): never {
  throw new HttpError(404, message);
}

export async function requireUser(event: HandlerEvent): Promise<AppUser> {
  const authorization =
    event.headers.authorization ?? event.headers.Authorization;

  if (!authorization?.startsWith("Bearer ")) {
    unauthorized("Missing bearer token.");
  }

  const token = authorization.replace("Bearer ", "");
  const session = await getSession(token);

  if (!session) {
    unauthorized("Invalid auth token.");
  }

  const user = await getUserById(session.user_id);
  if (!user) {
    unauthorized("User account not found.");
  }

  return user;
}

export async function requireUserId(event: HandlerEvent): Promise<string> {
  const user = await requireUser(event);
  return user.id;
}

export function isPost(event: HandlerEvent): boolean {
  return event.httpMethod.toUpperCase() === "POST";
}

function normalizeUnexpectedError(error: unknown) {
  const rawMessage =
    error instanceof Error ? error.message : "Unexpected server error.";

  if (/OPENAI_API_KEY/i.test(rawMessage)) {
    return {
      statusCode: 503,
      message:
        "MagicView is missing `OPENAI_API_KEY` in this deployment. Add it in Netlify before AI hand analysis will work.",
    };
  }

  return {
    statusCode: /missing|invalid|required|must|password|email/i.test(rawMessage)
      ? 400
      : 500,
    message: rawMessage,
  };
}

export async function withErrorBoundary(
  callback: () => Promise<HandlerResponse>,
): Promise<HandlerResponse> {
  try {
    return await callback();
  } catch (error) {
    if (error instanceof HttpError) {
      return jsonResponse(error.statusCode, {
        error: error.message,
      });
    }

    const normalized = normalizeUnexpectedError(error);

    return jsonResponse(normalized.statusCode, {
      error: normalized.message,
    });
  }
}
