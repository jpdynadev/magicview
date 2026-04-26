import type { Handler } from "@netlify/functions";

import { signUserToken, hashPassword } from "../../src/lib/server/auth";
import { queryOne } from "../../src/lib/server/db";
import {
  badRequest,
  isPost,
  jsonResponse,
  parseJsonBody,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
import { mapUserRow } from "../../src/lib/server/serializers";
import { validateEmail, validatePassword } from "../../src/lib/server/validators";
import type { AuthResponse } from "../../src/lib/types";

interface RegisterRequest {
  email: string;
  password: string;
}

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const request = parseJsonBody<RegisterRequest>(event);
    const email = validateEmail(request.email);
    const password = validatePassword(request.password);

    const existingUser = await queryOne<Record<string, unknown>>(
      `
        select id
        from users
        where email = $1
      `,
      [email],
    );

    if (existingUser) {
      badRequest("An account with that email already exists.");
    }

    const passwordHash = await hashPassword(password);
    const userRow = await queryOne<Record<string, unknown>>(
      `
        insert into users (email, password_hash)
        values ($1, $2)
        returning id, email, created_at
      `,
      [email, passwordHash],
    );

    if (!userRow) {
      throw new Error("Failed to create account.");
    }

    const user = mapUserRow(userRow);
    const token = await signUserToken(user);

    const response: AuthResponse = {
      token,
      user,
    };

    return jsonResponse(200, response);
  });

