import type { ParsedDeckEntry } from "@/lib/types";

const SECTION_HEADERS = new Set([
  "commander",
  "companions",
  "companion",
  "sideboard",
  "maybeboard",
  "deck",
  "mainboard",
]);

export function normalizeCardName(value: string): string {
  return value
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\u2019/g, "'")
    .toLowerCase();
}

function cleanLine(line: string): string {
  return line
    .replace(/\s*#.*$/, "")
    .replace(/\s*\/\/.*$/, "")
    .trim();
}

export function parseDecklist(decklistText: string): ParsedDeckEntry[] {
  const entries = new Map<string, ParsedDeckEntry>();

  for (const rawLine of decklistText.split(/\r?\n/)) {
    const line = cleanLine(rawLine);
    if (!line) {
      continue;
    }

    const lower = line.toLowerCase().replace(/:$/, "");
    if (SECTION_HEADERS.has(lower)) {
      continue;
    }

    const qtyPrefixMatch = line.match(/^(\d+)x?\s+(.+)$/i);
    const qtySuffixMatch = line.match(/^(.+?)\s+x?(\d+)$/i);

    const quantity = qtyPrefixMatch
      ? Number(qtyPrefixMatch[1])
      : qtySuffixMatch
        ? Number(qtySuffixMatch[2])
        : 1;

    const name = qtyPrefixMatch
      ? qtyPrefixMatch[2]
      : qtySuffixMatch
        ? qtySuffixMatch[1]
        : line;

    const normalized = normalizeCardName(name);
    const existing = entries.get(normalized);

    if (existing) {
      existing.quantity += quantity;
      continue;
    }

    entries.set(normalized, {
      quantity,
      cardName: name.trim(),
    });
  }

  return Array.from(entries.values()).sort((a, b) =>
    a.cardName.localeCompare(b.cardName),
  );
}

export function parseHandInput(handText: string): string[] {
  return handText
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => item.replace(/^\d+x?\s+/i, "").trim());
}

export function splitCommanders(commanderField: string): string[] {
  return commanderField
    .split(/,|\/|&/)
    .map((value) => value.trim())
    .filter(Boolean);
}

