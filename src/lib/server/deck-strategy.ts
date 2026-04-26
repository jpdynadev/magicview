import { deckTagBreakdown } from "@/lib/card-tags";
import type { CachedCard } from "@/lib/types";

export function buildDeckStrategySummary(input: {
  commanders: CachedCard[];
  deckCards: CachedCard[];
  existingSummary?: string | null;
}): string {
  const existing = input.existingSummary?.trim();
  if (existing) {
    return existing;
  }

  const commanderSummary = input.commanders.length
    ? input.commanders
        .map((card) => card.compact_summary || `${card.name} is the commander.`)
        .join(" ")
    : "Commander profile is still being cached.";

  const topTags = deckTagBreakdown(input.deckCards)
    .filter(([tag]) => tag !== "land" && tag !== "creature")
    .slice(0, 4)
    .map(([tag]) => tag.replace(/_/g, " "));

  const strategySentence = topTags.length
    ? `Deck signals skew toward ${topTags.join(", ")}.`
    : "Deck signals are still sparse, so use the opening hand and commander text more heavily.";

  return `${commanderSummary} ${strategySentence}`.trim();
}

