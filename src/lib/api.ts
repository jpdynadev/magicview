"use client";

import { getStoredAuthToken } from "@/lib/auth-storage";

interface FunctionCallOptions {
  requireAuth?: boolean;
  token?: string | null;
}

export async function callNetlifyFunction<TResponse>(
  functionName: string,
  payload: Record<string, unknown>,
  options: FunctionCallOptions = {},
): Promise<TResponse> {
  const token = options.token ?? getStoredAuthToken();

  if (options.requireAuth !== false && !token) {
    throw new Error("You must be signed in to perform this action.");
  }

  const response = await fetch(`/.netlify/functions/${functionName}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });

  const body = (await response.json()) as TResponse & { error?: string };

  if (!response.ok) {
    throw new Error(body.error ?? "Request failed.");
  }

  return body;
}

export async function callPublicNetlifyFunction<TResponse>(
  functionName: string,
  payload: Record<string, unknown>,
) {
  return callNetlifyFunction<TResponse>(functionName, payload, {
    requireAuth: false,
  });
}
