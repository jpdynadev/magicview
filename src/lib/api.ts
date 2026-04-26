"use client";

import { getSupabaseBrowserClient } from "@/lib/supabase-browser";

export async function callNetlifyFunction<TResponse>(
  functionName: string,
  payload: Record<string, unknown>,
): Promise<TResponse> {
  const supabase = getSupabaseBrowserClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    throw new Error("You must be signed in to perform this action.");
  }

  const response = await fetch(`/.netlify/functions/${functionName}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify(payload),
  });

  const body = (await response.json()) as TResponse & { error?: string };

  if (!response.ok) {
    throw new Error(body.error ?? "Request failed.");
  }

  return body;
}

