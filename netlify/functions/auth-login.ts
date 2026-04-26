import type { Handler } from "@netlify/functions";

import { signUserToken, verifyPassword } from "../../src/lib/server/auth";
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

interface LoginRequest {
  email: string;
  password: string;
}

export const handler: Handler = async (event) =>
  withErrorBoundary(async () => {
    if (!isPost(event)) {
      return jsonResponse(405, { error: "Method not allowed." });
    }

    const request = parseJsonBody<LoginRequest>(event);
    const email = validateEmail(request.email);
    const password = validatePassword(request.password);

    const userRow = await queryOne<Record<string, unknown>>(
      `
        select id, email, created_at, password_hash
        from users
        where email = $1
      `,
      [email],
    );

    if (!userRow?.password_hash) {
      badRequest("Invalid email or password.");
    }

    const passwordMatches = await verifyPassword(
      password,
      String(userRow.password_hash),
    );

    if (!passwordMatches) {
      badRequest("Invalid email or password.");
    }

    const user = mapUserRow(userRow);
    const token = await signUserToken(user);

    const response: AuthResponse = {
      token,
      user,
    };

    return jsonResponse(200, response);
  });

