import type { SupabaseClient } from "@supabase/supabase-js";

import { parseCardSignals } from "@/lib/card-tags";
import { normalizeCardName } from "@/lib/decklist";
import { serverEnv } from "@/lib/env";
import type { CachedCard } from "@/lib/types";
import { cardCompressionJsonSchema } from "@/lib/server/ai-schemas";
import { getStructuredOutputText } from "@/lib/server/openai-structured";
import { getOpenAIClient } from "@/lib/server/openai";
import { getSupabaseAdminClient } from "@/lib/server/supabase-admin";

interface ScryfallCardFace {
  oracle_text?: string;
  type_line?: string;
  mana_cost?: string;
}

interface ScryfallCard {
  id: string;
  name: string;
  cmc?: number;
  type_line?: string;
  oracle_text?: string;
  color_identity?: string[];
  image_uris?: {
    normal?: string;
  };
  card_faces?: ScryfallCardFace[];
}

interface CompressionResult {
  compact_summary: string;
  primary_abilities: string[];
  secondary_abilities: string[];
  strategic_tags: string[];
  mulligan_relevance_score: number;
}

interface EnsureCardsResult {
  cards: Map<string, CachedCard>;
  unresolved: string[];
}

interface CardUpsertRecord {
  scryfall_id: string;
  name: string;
  name_normalized: string;
  mana_value: number | null;
  type_line: string | null;
  oracle_text: string | null;
  colors: string[];
  tags: string[];
  compact_summary: string;
  primary_abilities: string[];
  secondary_abilities: string[];
  mulligan_relevance_score: number;
  image_uri: string | null;
}

function dedupeNames(names: string[]): Array<{ original: string; normalized: string }> {
  const unique = new Map<string, string>();

  for (const name of names) {
    const normalized = normalizeCardName(name);
    if (normalized) {
      unique.set(normalized, name.trim());
    }
  }

  return Array.from(unique.entries()).map(([normalized, original]) => ({
    original,
    normalized,
  }));
}

function collectOracleText(card: ScryfallCard): string {
  if (card.oracle_text) {
    return card.oracle_text;
  }

  return (card.card_faces ?? [])
    .map((face) => face.oracle_text)
    .filter(Boolean)
    .join("\n");
}

function collectTypeLine(card: ScryfallCard): string {
  if (card.type_line) {
    return card.type_line;
  }

  return (card.card_faces ?? [])
    .map((face) => face.type_line)
    .filter(Boolean)
    .join(" // ");
}

function baseCardRecord(card: ScryfallCard): CardUpsertRecord {
  const typeLine = collectTypeLine(card);
  const oracleText = collectOracleText(card);
  const parsed = parseCardSignals(card.name, typeLine, oracleText);

  return {
    scryfall_id: card.id,
    name: card.name,
    name_normalized: normalizeCardName(card.name),
    mana_value: typeof card.cmc === "number" ? card.cmc : null,
    type_line: typeLine || null,
    oracle_text: oracleText || null,
    colors: card.color_identity ?? [],
    tags: parsed.tags,
    compact_summary: parsed.fallbackSummary,
    primary_abilities: [],
    secondary_abilities: [],
    mulligan_relevance_score: parsed.tags.includes("land")
      ? 9
      : parsed.tags.some((tag) => ["ramp", "draw", "mana_generation"].includes(tag))
        ? 8
        : 5,
    image_uri: card.image_uris?.normal ?? null,
  };
}

async function fetchScryfallCard(name: string): Promise<ScryfallCard> {
  const response = await fetch(
    `https://api.scryfall.com/cards/named?fuzzy=${encodeURIComponent(name)}`,
    {
      headers: {
        "User-Agent": "MagicView MVP / https://github.com/jpdynadev/magicview",
      },
    },
  );

  if (!response.ok) {
    throw new Error(`Scryfall lookup failed for "${name}".`);
  }

  return (await response.json()) as ScryfallCard;
}

async function compressCardRecord(
  card: ReturnType<typeof baseCardRecord>,
): Promise<CompressionResult> {
  const client = getOpenAIClient();
  const response = await client.responses.create({
    model: serverEnv.cardCompressionModel,
    reasoning: { effort: "minimal" },
    input: [
      {
        role: "system",
        content: [
          {
            type: "input_text",
            text:
              "Compress Magic: The Gathering Commander card data. Use only the provided oracle text and parsed tags. Keep the summary to one sentence and do not invent synergies beyond the visible text.",
          },
        ],
      },
      {
        role: "user",
        content: [
          {
            type: "input_text",
            text: JSON.stringify(
              {
                name: card.name,
                oracle_text: card.oracle_text,
                parsed_tags: card.tags,
              },
              null,
              2,
            ),
          },
        ],
      },
    ],
    text: {
      format: {
        type: "json_schema",
        name: "card_compression",
        strict: true,
        schema: cardCompressionJsonSchema,
      },
    },
  });

  return JSON.parse(getStructuredOutputText(response)) as CompressionResult;
}

async function upsertCard(
  supabase: SupabaseClient,
  card: ReturnType<typeof baseCardRecord>,
  options?: { compressWithAi?: boolean },
): Promise<CachedCard> {
  const shouldCompress = options?.compressWithAi ?? true;
  let record: CardUpsertRecord = { ...card };

  if (shouldCompress) {
    try {
      const compressed = await compressCardRecord(card);
      record = {
        ...record,
        compact_summary: compressed.compact_summary,
        primary_abilities: compressed.primary_abilities,
        secondary_abilities: compressed.secondary_abilities,
        mulligan_relevance_score: compressed.mulligan_relevance_score,
        tags: Array.from(new Set([...record.tags, ...compressed.strategic_tags])).sort(),
      };
    } catch {
      // Fallback remains deterministic so deck import still works.
    }
  }

  const { data, error } = await supabase
    .from("cards")
    .upsert(record, {
      onConflict: "name_normalized",
    })
    .select(
      "name,name_normalized,mana_value,type_line,oracle_text,colors,tags,compact_summary,primary_abilities,secondary_abilities,mulligan_relevance_score,image_uri",
    )
    .single();

  if (error || !data) {
    throw new Error(`Failed to cache card "${card.name}".`);
  }

  return data as CachedCard;
}

async function batchMap<TInput, TResult>(
  items: TInput[],
  batchSize: number,
  callback: (item: TInput) => Promise<TResult>,
): Promise<TResult[]> {
  const results: TResult[] = [];

  for (let index = 0; index < items.length; index += batchSize) {
    const slice = items.slice(index, index + batchSize);
    const sliceResults = await Promise.all(slice.map(callback));
    results.push(...sliceResults);
  }

  return results;
}

export async function ensureCardsCached(
  names: string[],
  options?: { compressWithAi?: boolean; supabase?: SupabaseClient },
): Promise<EnsureCardsResult> {
  const supabase = options?.supabase ?? getSupabaseAdminClient();
  const uniqueNames = dedupeNames(names);

  if (!uniqueNames.length) {
    return {
      cards: new Map(),
      unresolved: [],
    };
  }

  const normalizedNames = uniqueNames.map((entry) => entry.normalized);
  const { data: existingRows, error } = await supabase
    .from("cards")
    .select(
      "name,name_normalized,mana_value,type_line,oracle_text,colors,tags,compact_summary,primary_abilities,secondary_abilities,mulligan_relevance_score,image_uri",
    )
    .in("name_normalized", normalizedNames);

  if (error) {
    throw new Error("Failed to query cached cards.");
  }

  const cards = new Map<string, CachedCard>();
  for (const row of (existingRows ?? []) as CachedCard[]) {
    cards.set(row.name_normalized, row);
  }

  const missing = uniqueNames.filter((entry) => !cards.has(entry.normalized));
  const unresolved: string[] = [];

  await batchMap(missing, 6, async (entry) => {
    try {
      const scryfallCard = await fetchScryfallCard(entry.original);
      const cached = await upsertCard(
        supabase,
        baseCardRecord(scryfallCard),
        options,
      );
      cards.set(cached.name_normalized, cached);
    } catch {
      unresolved.push(entry.original);
    }
  });

  return {
    cards,
    unresolved,
  };
}

export async function ingestScryfallCard(
  rawCard: ScryfallCard,
  options?: { compressWithAi?: boolean; supabase?: SupabaseClient },
): Promise<CachedCard> {
  const supabase = options?.supabase ?? getSupabaseAdminClient();
  return upsertCard(supabase, baseCardRecord(rawCard), options);
}
