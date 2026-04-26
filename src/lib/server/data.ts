import crypto from "node:crypto";

import { normalizeEmail } from "@/lib/server/validators";
import type {
  AppUser,
  CachedCard,
  Deck,
  DeckCard,
  GameSession,
  HandSnapshot,
} from "@/lib/types";
import {
  blobDelete,
  blobGetJson,
  blobListKeys,
  blobSetJson,
} from "@/lib/server/blob-store";

interface StoredUser {
  id: string;
  email: string;
  password_hash: string;
  created_at: string;
}

function nowIso() {
  return new Date().toISOString();
}

function keyUserByEmail(email: string) {
  return `users/by-email/${normalizeEmail(email)}`;
}

function keyUserById(userId: string) {
  return `users/by-id/${userId}`;
}

function keySession(token: string) {
  return `sessions/by-token/${token}`;
}

function keyDeck(deckId: string) {
  return `decks/by-id/${deckId}`;
}

function keyDeckIndex(userId: string) {
  return `decks/by-user/${userId}`;
}

function keyDeckCards(deckId: string) {
  return `deck-cards/by-deck/${deckId}`;
}

function keyCachedCard(nameNormalized: string) {
  return `cards/by-name/${nameNormalized}`;
}

function keyGameSession(sessionId: string) {
  return `game-sessions/by-id/${sessionId}`;
}

function keyGameSessionsIndex(deckId: string) {
  return `game-sessions/by-deck/${deckId}`;
}

function keyHandSnapshot(snapshotId: string) {
  return `hand-snapshots/by-id/${snapshotId}`;
}

function keyHandSnapshotsIndex(sessionId: string) {
  return `hand-snapshots/by-session/${sessionId}`;
}

async function readIndex(key: string): Promise<string[]> {
  return (await blobGetJson<string[]>(key)) ?? [];
}

async function writeIndex(key: string, values: string[]) {
  await blobSetJson(key, values);
}

function uniquePush(list: string[], value: string) {
  if (!list.includes(value)) list.push(value);
}

export async function createUser(params: {
  email: string;
  passwordHash: string;
}): Promise<{ user: AppUser; stored: StoredUser }> {
  const email = normalizeEmail(params.email);
  const existing = await blobGetJson<StoredUser>(keyUserByEmail(email));
  if (existing) {
    throw new Error("An account with that email already exists.");
  }

  const stored: StoredUser = {
    id: crypto.randomUUID(),
    email,
    password_hash: params.passwordHash,
    created_at: nowIso(),
  };

  await Promise.all([
    blobSetJson(keyUserByEmail(email), stored),
    blobSetJson(keyUserById(stored.id), stored),
  ]);

  return {
    stored,
    user: {
      id: stored.id,
      email: stored.email,
      created_at: stored.created_at,
    },
  };
}

export async function getUserById(userId: string): Promise<AppUser | null> {
  const stored = await blobGetJson<StoredUser>(keyUserById(userId));
  if (!stored) return null;
  return { id: stored.id, email: stored.email, created_at: stored.created_at };
}

export async function getUserByEmail(
  email: string,
): Promise<StoredUser | null> {
  return blobGetJson<StoredUser>(keyUserByEmail(email));
}

export async function createSession(params: { userId: string; email: string }) {
  const token = crypto.randomBytes(32).toString("hex");
  await blobSetJson(keySession(token), {
    user_id: params.userId,
    email: normalizeEmail(params.email),
    created_at: nowIso(),
  });
  return token;
}

export async function getSession(token: string): Promise<{
  user_id: string;
  email: string;
  created_at: string;
} | null> {
  return blobGetJson(keySession(token));
}

export async function deleteSession(token: string) {
  await blobDelete(keySession(token));
}

export async function upsertDeck(params: {
  deckId?: string;
  userId: string;
  name: string;
  commander: string;
  bracket: number;
  strategy_summary: string | null;
}): Promise<Deck> {
  const deckId = params.deckId ?? crypto.randomUUID();
  const existing = await blobGetJson<Deck>(keyDeck(deckId));
  const createdAt = existing?.created_at ?? nowIso();
  const deck: Deck = {
    id: deckId,
    user_id: params.userId,
    name: params.name,
    commander: params.commander,
    bracket: params.bracket,
    strategy_summary: params.strategy_summary,
    created_at: createdAt,
    updated_at: nowIso(),
  };

  await blobSetJson(keyDeck(deckId), deck);

  const index = await readIndex(keyDeckIndex(params.userId));
  uniquePush(index, deckId);
  await writeIndex(keyDeckIndex(params.userId), index);

  return deck;
}

export async function replaceDeckCards(params: {
  deckId: string;
  cards: Array<{ card_name: string; quantity: number }>;
}): Promise<DeckCard[]> {
  const deckCards: DeckCard[] = params.cards.map((card) => ({
    id: crypto.randomUUID(),
    deck_id: params.deckId,
    card_name: card.card_name,
    quantity: card.quantity,
  }));

  await blobSetJson(keyDeckCards(params.deckId), deckCards);
  return deckCards;
}

export async function listDecksByUser(userId: string): Promise<Deck[]> {
  const deckIds = await readIndex(keyDeckIndex(userId));
  const decks = await Promise.all(deckIds.map((id) => blobGetJson<Deck>(keyDeck(id))));
  return decks
    .filter(Boolean)
    .sort((a, b) => (b!.created_at > a!.created_at ? 1 : -1)) as Deck[];
}

export async function getDeckById(
  deckId: string,
): Promise<Deck | null> {
  return blobGetJson<Deck>(keyDeck(deckId));
}

export async function getDeckCards(deckId: string): Promise<DeckCard[]> {
  return (await blobGetJson<DeckCard[]>(keyDeckCards(deckId))) ?? [];
}

export async function upsertCachedCard(card: CachedCard) {
  await blobSetJson(keyCachedCard(card.name_normalized), card);
}

export async function getCachedCard(
  nameNormalized: string,
): Promise<CachedCard | null> {
  return blobGetJson<CachedCard>(keyCachedCard(nameNormalized));
}

export async function createGameSession(params: {
  deckId: string;
}): Promise<GameSession> {
  const session: GameSession = {
    id: crypto.randomUUID(),
    deck_id: params.deckId,
    created_at: nowIso(),
  };

  await blobSetJson(keyGameSession(session.id), session);
  const index = await readIndex(keyGameSessionsIndex(params.deckId));
  uniquePush(index, session.id);
  await writeIndex(keyGameSessionsIndex(params.deckId), index);

  return session;
}

export async function getGameSession(
  sessionId: string,
): Promise<GameSession | null> {
  return blobGetJson<GameSession>(keyGameSession(sessionId));
}

export async function listGameSessionsForDeck(deckId: string): Promise<GameSession[]> {
  const ids = await readIndex(keyGameSessionsIndex(deckId));
  const sessions = await Promise.all(ids.map((id) => blobGetJson<GameSession>(keyGameSession(id))));
  return (sessions.filter(Boolean) as GameSession[]).sort((a, b) =>
    b.created_at > a.created_at ? 1 : -1,
  );
}

export async function createHandSnapshot(params: {
  sessionId: string;
  mulligan_number: number;
  seat_position: string;
  cards: unknown;
  decision: string;
  confidence: number;
  reasoning: string[];
  turn_plan: unknown;
}): Promise<HandSnapshot> {
  const snapshotId = crypto.randomUUID();
  const snapshot: HandSnapshot = {
    id: snapshotId,
    session_id: params.sessionId,
    mulligan_number: params.mulligan_number,
    seat_position: params.seat_position as HandSnapshot["seat_position"],
    cards: params.cards as HandSnapshot["cards"],
    decision: params.decision as HandSnapshot["decision"],
    confidence: params.confidence,
    reasoning: params.reasoning,
    turn_plan: params.turn_plan as HandSnapshot["turn_plan"],
    created_at: nowIso(),
  };

  await blobSetJson(keyHandSnapshot(snapshotId), snapshot);
  const index = await readIndex(keyHandSnapshotsIndex(params.sessionId));
  uniquePush(index, snapshotId);
  await writeIndex(keyHandSnapshotsIndex(params.sessionId), index);

  return snapshot;
}

export async function listHandSnapshotsForSession(sessionId: string): Promise<HandSnapshot[]> {
  const ids = await readIndex(keyHandSnapshotsIndex(sessionId));
  const snapshots = await Promise.all(ids.map((id) => blobGetJson<HandSnapshot>(keyHandSnapshot(id))));
  return (snapshots.filter(Boolean) as HandSnapshot[]).sort((a, b) =>
    b.created_at > a.created_at ? 1 : -1,
  );
}

export async function listHandSnapshotsForDeck(deckId: string): Promise<HandSnapshot[]> {
  // Slow path for MVP: scan all snapshots and filter by deck sessions.
  const sessionIds = await readIndex(keyGameSessionsIndex(deckId));
  const all = await Promise.all(sessionIds.map((id) => listHandSnapshotsForSession(id)));
  return all.flat().sort((a, b) => (b.created_at > a.created_at ? 1 : -1));
}

export async function getHandSnapshot(snapshotId: string): Promise<HandSnapshot | null> {
  return blobGetJson<HandSnapshot>(keyHandSnapshot(snapshotId));
}

export async function listAllCachedCardsKeys(): Promise<string[]> {
  return blobListKeys("cards/by-name/");
}

