import type { HandlerEvent, HandlerResponse } from "@netlify/functions";

import { verifyUserToken } from "@/lib/server/auth";
import { queryOne } from "@/lib/server/db";
import { mapUserRow } from "@/lib/server/serializers";
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
  const payload = await verifyUserToken(token).catch(() =>
    unauthorized("Invalid auth token."),
  );

  const userRow = await queryOne<Record<string, unknown>>(
    `
      select id, email, created_at
      from users
      where id = $1 and email = $2
    `,
    [payload.sub, payload.email],
  );

  if (!userRow) {
    unauthorized("User account not found.");
  }

  return mapUserRow(userRow);
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

  if (
    /DATABASE_URL|NETLIFY_DATABASE_URL|POSTGRES_URL|NEON_DATABASE_URL/i.test(
      rawMessage,
    )
  ) {
    return {
      statusCode: 503,
      message:
        "MagicView is missing a Postgres database connection in this deployment. Add `DATABASE_URL` in Netlify before auth and saved deck features will work.",
    };
  }

  if (/MAGICVIEW_JWT_SECRET/i.test(rawMessage)) {
    return {
      statusCode: 503,
      message:
        "MagicView is missing `MAGICVIEW_JWT_SECRET` in this deployment. Add it in Netlify before auth will work.",
    };
  }

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
