import { normalizeCardName } from "@/lib/decklist";
import type {
  CachedCard,
  MulliganAnalysisResult,
  MulliganPromptPayload,
  StoredHandCard,
} from "@/lib/types";
import { mulliganDecisionJsonSchema } from "@/lib/server/ai-schemas";
import { getOpenAIClient } from "@/lib/server/openai";
import { getStructuredOutputText } from "@/lib/server/openai-structured";
import { serverEnv } from "@/lib/env";

export function buildStoredHandCards(cards: CachedCard[]): StoredHandCard[] {
  return cards.map((card) => ({
    name: card.name,
    summary: card.compact_summary || `${card.name} has no cached summary yet.`,
    tags: card.tags ?? [],
  }));
}

export function alignCardsToInput(
  requestedNames: string[],
  cardMap: Map<string, CachedCard>,
): CachedCard[] {
  return requestedNames.map((name) => {
    const card = cardMap.get(normalizeCardName(name));
    if (!card) {
      throw new Error(`Could not resolve card "${name}" from the cache.`);
    }
    return card;
  });
}

export async function analyzeOpeningHand(
  payload: MulliganPromptPayload,
): Promise<MulliganAnalysisResult> {
  const client = getOpenAIClient();
  const response = await client.responses.create({
    model: serverEnv.mulliganModel,
    reasoning: { effort: "low" },
    input: [
      {
        role: "system",
        content: [
          {
            type: "input_text",
            text:
              "You are MagicView, an MTG Commander mulligan evaluator. Use only the provided JSON payload. Consider bracket, commander plan, mana availability, ramp, synergy, interaction, and speed. Do not mention any card that is not present in the payload. If the hand is borderline, reflect that uncertainty in confidence and reasoning.",
          },
        ],
      },
      {
        role: "user",
        content: [
          {
            type: "input_text",
            text: JSON.stringify(payload, null, 2),
          },
        ],
      },
    ],
    text: {
      format: {
        type: "json_schema",
        name: "mulligan_analysis",
        strict: true,
        schema: mulliganDecisionJsonSchema,
      },
    },
  });

  return JSON.parse(getStructuredOutputText(response)) as MulliganAnalysisResult;
}

