import { parseCardSignals } from "@/lib/card-tags";
import { normalizeCardName } from "@/lib/decklist";
import { serverEnv } from "@/lib/env";
import { cardCompressionJsonSchema } from "@/lib/server/ai-schemas";
import { getOpenAIClient } from "@/lib/server/openai";
import { getStructuredOutputText } from "@/lib/server/openai-structured";
import { CARD_SELECT_COLUMNS } from "@/lib/server/queries";
import { queryMany } from "@/lib/server/db";
import { mapCachedCardRow } from "@/lib/server/serializers";
import type { CachedCard } from "@/lib/types";

interface ScryfallCardFace {
  oracle_text?: string;
  type_line?: string;
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
      // Deterministic fallback still provides useful cache coverage.
    }
  }

  const rows = await queryMany<Record<string, unknown>>(
    `
      insert into cards (
        scryfall_id,
        name,
        name_normalized,
        mana_value,
        type_line,
        oracle_text,
        colors,
        tags,
        compact_summary,
        primary_abilities,
        secondary_abilities,
        mulligan_relevance_score,
        image_uri
      )
      values (
        $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11, $12, $13
      )
      on conflict (name_normalized) do update set
        scryfall_id = excluded.scryfall_id,
        name = excluded.name,
        mana_value = excluded.mana_value,
        type_line = excluded.type_line,
        oracle_text = excluded.oracle_text,
        colors = excluded.colors,
        tags = excluded.tags,
        compact_summary = excluded.compact_summary,
        primary_abilities = excluded.primary_abilities,
        secondary_abilities = excluded.secondary_abilities,
        mulligan_relevance_score = excluded.mulligan_relevance_score,
        image_uri = excluded.image_uri,
        updated_at = timezone('utc', now())
      returning ${CARD_SELECT_COLUMNS}
    `,
    [
      record.scryfall_id,
      record.name,
      record.name_normalized,
      record.mana_value,
      record.type_line,
      record.oracle_text,
      record.colors,
      JSON.stringify(record.tags),
      record.compact_summary,
      record.primary_abilities,
      record.secondary_abilities,
      record.mulligan_relevance_score,
      record.image_uri,
    ],
  );

  const row = rows[0];
  if (!row) {
    throw new Error(`Failed to cache card "${card.name}".`);
  }

  return mapCachedCardRow(row as Record<string, unknown>);
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
  options?: { compressWithAi?: boolean },
): Promise<EnsureCardsResult> {
  const uniqueNames = dedupeNames(names);

  if (!uniqueNames.length) {
    return {
      cards: new Map(),
      unresolved: [],
    };
  }

  const normalizedNames = uniqueNames.map((entry) => entry.normalized);
  const existingRows = await queryMany<Record<string, unknown>>(
    `
      select ${CARD_SELECT_COLUMNS}
      from cards
      where name_normalized = any($1)
    `,
    [normalizedNames],
  );

  const cards = new Map<string, CachedCard>();
  for (const row of existingRows) {
    const card = mapCachedCardRow(row);
    cards.set(card.name_normalized, card);
  }

  const missing = uniqueNames.filter((entry) => !cards.has(entry.normalized));
  const unresolved: string[] = [];

  await batchMap(missing, 6, async (entry) => {
    try {
      const scryfallCard = await fetchScryfallCard(entry.original);
      const cached = await upsertCard(baseCardRecord(scryfallCard), options);
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
  options?: { compressWithAi?: boolean },
): Promise<CachedCard> {
  return upsertCard(baseCardRecord(rawCard), options);
}
