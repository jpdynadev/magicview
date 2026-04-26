import type { Handler } from "@netlify/functions";

import { verifyPassword } from "../../src/lib/server/auth";
import { createSession, getUserByEmail } from "../../src/lib/server/data";
import {
  badRequest,
  isPost,
  jsonResponse,
  parseJsonBody,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
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

    const storedUser = await getUserByEmail(email);
    if (!storedUser) {
      badRequest("Invalid email or password.");
    }

    const passwordMatches = await verifyPassword(password, storedUser.password_hash);

    if (!passwordMatches) {
      badRequest("Invalid email or password.");
    }

    const user = {
      id: storedUser.id,
      email: storedUser.email,
      created_at: storedUser.created_at,
    };
    const token = await createSession({ userId: user.id, email: user.email });

    const response: AuthResponse = {
      token,
      user,
    };

    return jsonResponse(200, response);
  });
