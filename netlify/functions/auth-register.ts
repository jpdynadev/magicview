import type { Handler } from "@netlify/functions";

import { hashPassword } from "../../src/lib/server/auth";
import { createSession, createUser } from "../../src/lib/server/data";
import {
  isPost,
  jsonResponse,
  parseJsonBody,
  withErrorBoundary,
} from "../../src/lib/server/netlify";
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

    const passwordHash = await hashPassword(password);
    const { user } = await createUser({ email, passwordHash });
    const token = await createSession({ userId: user.id, email: user.email });

    const response: AuthResponse = {
      token,
      user,
    };

    return jsonResponse(200, response);
  });
