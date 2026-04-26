import type { CachedCard } from "@/lib/types";

export interface ParsedCardSignals {
  tags: string[];
  fallbackSummary: string;
}

const SIGNALS: Array<{ tag: string; matcher: RegExp }> = [
  { tag: "land", matcher: /\bland\b/i },
  { tag: "draw", matcher: /\bdraw\b|\binvestigate\b|\bconnive\b/i },
  { tag: "tutor", matcher: /\bsearch your library\b/i },
  {
    tag: "ramp",
    matcher:
      /\bsearch your library.*basic land\b|\byou may play an additional land\b|\btreasure token\b|\badd \{[^}]+\}\b/i,
  },
  {
    tag: "removal",
    matcher:
      /\bdestroy target\b|\bexile target\b|\bfight target\b|\bdeals \d+ damage to target\b/i,
  },
  { tag: "counterspell", matcher: /\bcounter target\b/i },
  { tag: "etb", matcher: /\benters the battlefield\b|\bwhen .* enters the battlefield\b/i },
  {
    tag: "mana_generation",
    matcher: /\badd \{[^}]+\}\b|\bcreate .* treasure\b|\bcreate .* mana\b/i,
  },
  { tag: "token-maker", matcher: /\bcreate (?:a|two|three|\d+)? ?.* token\b/i },
  { tag: "recursion", matcher: /\breturn target .* from your graveyard\b/i },
  { tag: "wipe", matcher: /\bdestroy all\b|\bexile all\b/i },
  { tag: "protection", matcher: /\bhexproof\b|\bindestructible\b|\bward\b/i },
];

export function parseCardSignals(
  name: string,
  typeLine?: string | null,
  oracleText?: string | null,
): ParsedCardSignals {
  const tags = new Set<string>();
  const combined = `${typeLine ?? ""}\n${oracleText ?? ""}`;

  if (/\bbasic land\b|\bland\b/i.test(typeLine ?? "")) {
    tags.add("land");
    tags.add("mana_generation");
  }

  if (/\bartifact\b/i.test(typeLine ?? "") && /\badd \{[^}]+\}\b/i.test(oracleText ?? "")) {
    tags.add("mana-rock");
  }

  if (/\bcreature\b/i.test(typeLine ?? "")) {
    tags.add("creature");
  }

  for (const signal of SIGNALS) {
    if (signal.matcher.test(combined)) {
      tags.add(signal.tag);
    }
  }

  const orderedTags = Array.from(tags).sort();
  const summaryParts: string[] = [];

  if (typeLine) {
    summaryParts.push(typeLine);
  }
  if (orderedTags.length > 0) {
    summaryParts.push(`signals: ${orderedTags.join(", ")}`);
  }
  if (!summaryParts.length) {
    summaryParts.push("Magic card with no compressed summary yet");
  }

  return {
    tags: orderedTags,
    fallbackSummary: `${name} is a ${summaryParts.join(" with ")}.`,
  };
}

export function deckTagBreakdown(cards: CachedCard[]): Array<[string, number]> {
  const counts = new Map<string, number>();

  for (const card of cards) {
    for (const tag of card.tags ?? []) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }

  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
}

