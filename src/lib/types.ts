export type MulliganDecision = "KEEP" | "MULLIGAN";

export type SeatPosition = "first" | "middle" | "last";

export interface AppUser {
  id: string;
  email: string;
  created_at: string;
}

export interface Deck {
  id: string;
  user_id: string;
  name: string;
  commander: string;
  bracket: number;
  strategy_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeckCard {
  id: string;
  deck_id: string;
  card_name: string;
  quantity: number;
}

export interface CachedCard {
  name: string;
  name_normalized: string;
  mana_value: number | null;
  type_line: string | null;
  oracle_text: string | null;
  colors: string[];
  tags: string[];
  compact_summary: string | null;
  primary_abilities: string[];
  secondary_abilities: string[];
  mulligan_relevance_score: number | null;
  image_uri: string | null;
}

export interface GameSession {
  id: string;
  deck_id: string;
  created_at: string;
}

export interface TurnPlan {
  turn_1: string;
  turn_2: string;
  turn_3: string;
}

export interface StoredHandCard {
  name: string;
  summary: string;
  tags: string[];
}

export interface HandSnapshot {
  id: string;
  session_id: string;
  mulligan_number: number;
  seat_position: SeatPosition;
  cards: StoredHandCard[];
  decision: MulliganDecision;
  confidence: number;
  reasoning: string[];
  turn_plan: TurnPlan;
  created_at: string;
}

export interface ParsedDeckEntry {
  quantity: number;
  cardName: string;
}

export interface MulliganPromptCard {
  name: string;
  summary: string;
  tags: string[];
}

export interface MulliganPromptPayload {
  commander: string;
  bracket: number;
  deck_strategy: string;
  opening_hand: MulliganPromptCard[];
  seat_position: SeatPosition;
  mulligan_number: number;
}

export interface MulliganAnalysisResult {
  decision: MulliganDecision;
  confidence: number;
  reasoning: string[];
  turn_plan: TurnPlan;
}

export interface UpsertDeckRequest {
  deckId?: string;
  name: string;
  commander: string;
  bracket: number;
  strategySummary?: string;
  decklistText: string;
}

export interface UpsertDeckResponse {
  deckId: string;
  strategySummary: string;
  parsedCards: number;
  unresolvedCards: string[];
}

export interface StartSessionRequest {
  deckId: string;
}

export interface StartSessionResponse {
  sessionId: string;
  createdAt: string;
}

export interface AuthResponse {
  token: string;
  user: AppUser;
}

export interface MeResponse {
  user: AppUser;
}

export interface AnalyzeHandRequest {
  sessionId: string;
  openingHandText: string;
  mulliganNumber: number;
  seatPosition: SeatPosition;
}

export interface AnalyzeHandResponse {
  sessionId: string;
  snapshotId: string;
  result: MulliganAnalysisResult;
}

export interface SessionDeckSummary {
  deck: Deck;
  cards: DeckCard[];
  recentHands: Array<HandSnapshot & { session_created_at?: string }>;
}

export interface ListDecksResponse {
  decks: Deck[];
}

export interface DeckDetailResponse {
  deck: Deck;
  cards: DeckCard[];
  sessions: GameSession[];
  snapshots: HandSnapshot[];
}

export interface ResultDetailResponse {
  session: GameSession;
  deck: Deck;
  snapshot: HandSnapshot;
}

