import type {
  AppUser,
  CachedCard,
  Deck,
  DeckCard,
  GameSession,
  HandSnapshot,
  StoredHandCard,
  TurnPlan,
} from "@/lib/types";

function parseJson<T>(value: unknown, fallback: T): T {
  if (value == null) {
    return fallback;
  }

  if (typeof value === "string") {
    try {
      return JSON.parse(value) as T;
    } catch {
      return fallback;
    }
  }

  return value as T;
}

function parseStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item));
  }

  return parseJson<string[]>(value, []);
}

function parseStoredHandCards(value: unknown): StoredHandCard[] {
  const cards = parseJson<StoredHandCard[]>(value, []);
  return Array.isArray(cards) ? cards : [];
}

function parseTurnPlan(value: unknown): TurnPlan {
  const turnPlan = parseJson<Partial<TurnPlan>>(value, {});
  return {
    turn_1: turnPlan.turn_1 ?? "",
    turn_2: turnPlan.turn_2 ?? "",
    turn_3: turnPlan.turn_3 ?? "",
  };
}

export function mapUserRow(row: Record<string, unknown>): AppUser {
  return {
    id: String(row.id),
    email: String(row.email),
    created_at: String(row.created_at),
  };
}

export function mapDeckRow(row: Record<string, unknown>): Deck {
  return {
    id: String(row.id),
    user_id: String(row.user_id),
    name: String(row.name),
    commander: String(row.commander),
    bracket: Number(row.bracket),
    strategy_summary:
      row.strategy_summary == null ? null : String(row.strategy_summary),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

export function mapDeckCardRow(row: Record<string, unknown>): DeckCard {
  return {
    id: String(row.id),
    deck_id: String(row.deck_id),
    card_name: String(row.card_name),
    quantity: Number(row.quantity),
  };
}

export function mapGameSessionRow(row: Record<string, unknown>): GameSession {
  return {
    id: String(row.id),
    deck_id: String(row.deck_id),
    created_at: String(row.created_at),
  };
}

export function mapHandSnapshotRow(row: Record<string, unknown>): HandSnapshot {
  return {
    id: String(row.id),
    session_id: String(row.session_id),
    mulligan_number: Number(row.mulligan_number),
    seat_position: row.seat_position as HandSnapshot["seat_position"],
    cards: parseStoredHandCards(row.cards),
    decision: row.decision as HandSnapshot["decision"],
    confidence: Number(row.confidence),
    reasoning: parseStringArray(row.reasoning),
    turn_plan: parseTurnPlan(row.turn_plan),
    created_at: String(row.created_at),
  };
}

export function mapCachedCardRow(row: Record<string, unknown>): CachedCard {
  return {
    name: String(row.name),
    name_normalized: String(row.name_normalized),
    mana_value: row.mana_value == null ? null : Number(row.mana_value),
    type_line: row.type_line == null ? null : String(row.type_line),
    oracle_text: row.oracle_text == null ? null : String(row.oracle_text),
    colors: parseStringArray(row.colors),
    tags: parseStringArray(row.tags),
    compact_summary:
      row.compact_summary == null ? null : String(row.compact_summary),
    primary_abilities: parseStringArray(row.primary_abilities),
    secondary_abilities: parseStringArray(row.secondary_abilities),
    mulligan_relevance_score:
      row.mulligan_relevance_score == null
        ? null
        : Number(row.mulligan_relevance_score),
    image_uri: row.image_uri == null ? null : String(row.image_uri),
  };
}

