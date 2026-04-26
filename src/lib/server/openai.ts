import OpenAI from "openai";

import { serverEnv } from "@/lib/env";

let client: OpenAI | undefined;

export function getOpenAIClient(): OpenAI {
  client ??= new OpenAI({
    apiKey: serverEnv.openAiApiKey,
  });

  return client;
}

