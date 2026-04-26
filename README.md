# MagicView

MagicView is a deployable MVP for Magic: The Gathering Commander players. A user can create an account, import a deck, start a game session, paste a 7-card opening hand, and get a structured AI mulligan recommendation with confidence, reasoning, and a turn plan.

## Stack

- Frontend: Next.js App Router
- Backend: Netlify Functions
- Database: Postgres via Neon-compatible connection string
- Auth: Netlify Function-backed email/password auth with signed JWTs
- Card data: Scryfall bulk data + named card API fallback
- AI: OpenAI Responses API with structured JSON output

The MVP does not require Supabase. It also does not require a storage service because the shipped flow uses text hand input only.

## MVP Features

- Email/password signup and login
- Dashboard with deck list and recent saved hands
- Commander deck import by pasted decklist
- Commander and bracket selection
- Game session creation
- Opening-hand analysis for exactly 7 cards
- Saved hand snapshots with keep or mulligan decision, confidence, reasoning, and turn plan
- Cached card summaries with deterministic tags and optional AI compression

## Project Structure

```text
magicview/
├─ database/
│  └─ schema.sql
├─ netlify/
│  └─ functions/
│     ├─ analyze-hand.ts
│     ├─ auth-login.ts
│     ├─ auth-register.ts
│     ├─ get-deck.ts
│     ├─ get-result.ts
│     ├─ list-decks.ts
│     ├─ me.ts
│     ├─ start-session.ts
│     └─ upsert-deck.ts
├─ scripts/
│  └─ sync-scryfall.ts
├─ src/
│  ├─ app/
│  │  ├─ auth/page.tsx
│  │  ├─ dashboard/page.tsx
│  │  ├─ decks/[deckId]/page.tsx
│  │  ├─ decks/[deckId]/start-game/page.tsx
│  │  ├─ sessions/[sessionId]/result/page.tsx
│  │  ├─ globals.css
│  │  ├─ layout.tsx
│  │  ├─ page.tsx
│  │  └─ providers.tsx
│  ├─ components/
│  │  ├─ auth/auth-card.tsx
│  │  ├─ auth/require-auth.tsx
│  │  ├─ dashboard/deck-list.tsx
│  │  ├─ decks/deck-editor.tsx
│  │  ├─ layout/app-shell.tsx
│  │  └─ session/result-card.tsx
│  └─ lib/
│     ├─ api.ts
│     ├─ auth-context.tsx
│     ├─ auth-storage.ts
│     ├─ card-tags.ts
│     ├─ decklist.ts
│     ├─ env.ts
│     ├─ types.ts
│     └─ server/
│        ├─ ai-schemas.ts
│        ├─ auth.ts
│        ├─ card-cache.ts
│        ├─ db.ts
│        ├─ deck-strategy.ts
│        ├─ hand-analysis.ts
│        ├─ netlify.ts
│        ├─ openai-structured.ts
│        ├─ openai.ts
│        ├─ queries.ts
│        ├─ serializers.ts
│        └─ validators.ts
├─ .env.example
├─ netlify.toml
└─ package.json
```

## Database Schema

The schema lives in [`database/schema.sql`](./database/schema.sql).

It creates:

- `users`
- `decks`
- `deck_cards`
- `cards`
- `game_sessions`
- `hand_snapshots`

Notable schema decisions:

- `users` stores `email` plus `password_hash`
- `cards.tags` and `hand_snapshots.cards` use `jsonb`
- `hand_snapshots.turn_plan` uses `jsonb`
- `decks.updated_at` and `cards.updated_at` are maintained by triggers

## Card Data Pipeline

### Runtime behavior

Deck import and hand analysis both call `ensureCardsCached()`.

If a card is missing from the local `cards` cache:

1. MagicView queries the Scryfall named-card API.
2. It deterministically tags the card.
3. It generates a fallback compact summary.
4. It optionally compresses the card with OpenAI.
5. It upserts the result into `cards`.

This keeps the MVP usable before a full bulk sync is run.

### Bulk ingest script

```bash
npm run scryfall:sync -- --download
```

Useful variants:

```bash
# Download and ingest the first 500 cards with deterministic tags only
npm run scryfall:sync -- --download --limit 500

# Ingest from an existing file and run AI compression
npm run scryfall:sync -- --file data/scryfall/oracle-cards.json --limit 250 --ai

# Resume later from an offset
npm run scryfall:sync -- --file data/scryfall/oracle-cards.json --offset 250 --limit 250 --ai
```

## AI Prompt Contract

The mulligan function sends a compact payload to OpenAI:

```json
{
  "commander": "Tivit, Seller of Secrets",
  "bracket": 3,
  "deck_strategy": "Esper artifact control deck that ramps into value engines and extra turns.",
  "opening_hand": [
    {
      "name": "Sol Ring",
      "summary": "Cheap mana rock that accelerates explosive starts.",
      "tags": ["ramp", "mana_generation", "mana-rock"]
    }
  ],
  "seat_position": "first",
  "mulligan_number": 0
}
```

The response is forced through a strict JSON schema:

```json
{
  "decision": "KEEP",
  "confidence": 0.86,
  "reasoning": [
    "You have stable mana and acceleration.",
    "The hand advances the commander plan early."
  ],
  "turn_plan": {
    "turn_1": "Play Command Tower, cast Sol Ring.",
    "turn_2": "Deploy Arcane Signet and hold interaction if needed.",
    "turn_3": "Advance the value engine or set up commander mana."
  }
}
```

## Netlify Functions

### Public functions

- `auth-register`: creates a user, hashes the password, returns `{ token, user }`
- `auth-login`: verifies credentials, returns `{ token, user }`

### Authenticated functions

- `me`: returns the current user from the bearer token
- `list-decks`: returns all decks owned by the current user
- `get-deck`: returns one deck with cards, sessions, and snapshots
- `get-result`: returns one saved hand result with its deck and session
- `upsert-deck`: parses a decklist, resolves cards, builds strategy summary, inserts or updates the deck
- `start-session`: creates a `game_sessions` row for a deck the user owns
- `analyze-hand`: resolves the seven cards, builds the AI payload, calls OpenAI, and stores the saved hand snapshot

## Local Setup

1. Create a Neon project or any Postgres database reachable from Netlify Functions.
2. Run [`database/schema.sql`](./database/schema.sql) against that database.
3. Copy `.env.example` to `.env.local`.
4. Fill in:

```bash
DATABASE_URL=postgres://...
MAGICVIEW_JWT_SECRET=replace-with-a-long-random-secret
OPENAI_API_KEY=...
OPENAI_MULLIGAN_MODEL=gpt-5.4-mini
OPENAI_CARD_COMPRESSION_MODEL=gpt-5.4-nano
```

5. Install dependencies:

```bash
npm install
```

6. Start local development:

```bash
npm run dev
```

7. Optional: run through Netlify's local runtime:

```bash
npx netlify dev
```

## Example API Calls

### Create an account

```bash
curl -X POST http://localhost:8888/.netlify/functions/auth-register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "you@playgroup.gg",
    "password": "supersecret123"
  }'
```

### Create or import a deck

```bash
curl -X POST http://localhost:8888/.netlify/functions/upsert-deck \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "name": "Tivit Turns",
    "commander": "Tivit, Seller of Secrets",
    "bracket": 3,
    "strategySummary": "Esper control-combo deck with artifact ramp and extra turns.",
    "decklistText": "1 Sol Ring\n1 Arcane Signet\n1 Command Tower\n1 Rhystic Study"
  }'
```

### Start a game session

```bash
curl -X POST http://localhost:8888/.netlify/functions/start-session \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "deckId": "YOUR_DECK_UUID"
  }'
```

### Analyze an opening hand

```bash
curl -X POST http://localhost:8888/.netlify/functions/analyze-hand \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "sessionId": "YOUR_SESSION_UUID",
    "openingHandText": "Command Tower\nIsland\nSol Ring\nArcane Signet\nRhystic Study\nSwords to Plowshares\nSmothering Tithe",
    "mulliganNumber": 0,
    "seatPosition": "first"
  }'
```

## Netlify Deployment

The repository already includes:

- `netlify.toml`
- Next.js production build config
- `netlify/functions` for all serverless endpoints

### Required environment variables

Set these in Netlify before a production deploy:

```bash
DATABASE_URL=postgres://...
MAGICVIEW_JWT_SECRET=replace-with-a-long-random-secret
OPENAI_API_KEY=...
OPENAI_MULLIGAN_MODEL=gpt-5.4-mini
OPENAI_CARD_COMPRESSION_MODEL=gpt-5.4-nano
```

The app also accepts these database env names if you already have them in Netlify:

- `NETLIFY_DATABASE_URL`
- `POSTGRES_URL`
- `NEON_DATABASE_URL`

### Deploy commands

Preview deploy:

```bash
npx netlify deploy --build
```

Production deploy:

```bash
npx netlify deploy --build --prod
```

## Verification

The repository currently passes:

```bash
npm run typecheck
npm run build
```

## Post-MVP Roadmap

### 1. Image recognition for hands

- Add image upload support
- Run OCR plus Scryfall matching
- Reuse the existing `analyze-hand` pipeline

### 2. Opponent tracking

- Add pod metadata, commanders seen, and pace indicators
- Let mulligan logic adapt to table speed and interaction density

### 3. Game outcome learning

- Track whether a kept hand converted into a strong or weak game
- Improve prompts and evaluations with outcome feedback

### 4. Deck optimization suggestions

- Surface repeated weak keep patterns
- Suggest cuts and adds based on role coverage and curve gaps

### 5. Similar hand detection

- Cluster saved hands by strategic role instead of exact card match
- Reuse prior evaluations to reduce cost and improve consistency
