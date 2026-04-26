# MagicView

MagicView is a deployable MVP for Magic: The Gathering Commander players. A user can create an account, import a deck, start a game session, paste a 7-card opening hand, and get a structured AI mulligan recommendation with confidence, reasoning, and a turn plan.

## Stack

- Frontend: Next.js App Router
- Backend: Netlify Functions
- Persistence: Netlify Blobs (zero database setup)
- Auth: Email/password with server-stored session tokens (Bearer token)
- Card data: Scryfall bulk data + named card API fallback
- AI: OpenAI Responses API with structured JSON output

This MVP does not require Supabase, Neon, or any Postgres connection string.

## MVP Features

- Email/password signup and login
- Dashboard with deck list and recent saved hands
- Commander deck import by pasted decklist
- Commander and bracket selection (1–5)
- Game session creation
- Opening-hand analysis for exactly 7 cards
- Saved hand snapshots with keep/mulligan decision, confidence, reasoning, and turn plan
- Cached Scryfall cards with deterministic tags and optional AI compression

## Project Structure

```text
magicview/
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
│        ├─ blob-store.ts
│        ├─ card-cache.ts
│        ├─ data.ts
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

## Persistence Model (Blobs)

The app uses a Netlify Blobs store named `magicview`.

It stores:

- Users keyed by `users/by-email/...` and `users/by-id/...` (passwords are hashed with bcrypt)
- Sessions keyed by `sessions/by-token/...` (bearer tokens are opaque, server-validated)
- Decks keyed by `decks/by-id/...` plus a per-user deck index
- Deck cards keyed by `deck-cards/by-deck/...`
- Cached cards keyed by `cards/by-name/...`
- Game sessions keyed by `game-sessions/by-id/...` plus a per-deck session index
- Hand snapshots keyed by `hand-snapshots/by-id/...` plus a per-session snapshot index

## Card Data Pipeline

### Runtime behavior

Deck import and hand analysis both call `ensureCardsCached()`.

If a card is missing from the local cache:

1. MagicView queries the Scryfall named-card API.
2. It deterministically tags the card.
3. It generates a fallback compact summary.
4. It optionally compresses the card with OpenAI.
5. It stores the cached card in Netlify Blobs.

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

- `auth-register`: creates a user and session, returns `{ token, user }`
- `auth-login`: verifies credentials and returns `{ token, user }`

### Authenticated functions

- `me`: returns the current user from the bearer token
- `list-decks`: returns all decks owned by the current user
- `get-deck`: returns one deck with cards, sessions, and snapshots
- `get-result`: returns one saved hand result with its deck and session
- `upsert-deck`: parses a decklist, resolves cards, builds strategy summary, inserts or updates the deck
- `start-session`: creates a new game session for a deck
- `analyze-hand`: resolves the seven cards, calls OpenAI, and stores the saved hand snapshot

## Local Setup

1. Copy `.env.example` to `.env.local`.
2. (Optional) Add OpenAI keys for hand analysis:

```bash
OPENAI_API_KEY=...
OPENAI_MULLIGAN_MODEL=gpt-5.4-mini
OPENAI_CARD_COMPRESSION_MODEL=gpt-5.4-nano
```

3. Install dependencies:

```bash
npm install
```

4. Run locally:

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
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
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
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -d '{
    "deckId": "YOUR_DECK_UUID"
  }'
```

### Analyze an opening hand

```bash
curl -X POST http://localhost:8888/.netlify/functions/analyze-hand \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
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

None for auth/decks/sessions/results.

For AI mulligan analysis, set:

```bash
OPENAI_API_KEY=...
OPENAI_MULLIGAN_MODEL=gpt-5.4-mini
OPENAI_CARD_COMPRESSION_MODEL=gpt-5.4-nano
```

### Deploy commands

```bash
npx netlify deploy --build --prod
```

## Verification

```bash
npm run typecheck
npm run build
```

## Post-MVP Roadmap

- Image recognition for hands (upload + OCR + Scryfall matching)
- Opponent tracking (pod meta, commanders seen, pace indicators)
- Game outcome learning (label kept hands with outcomes)
- Deck optimization suggestions (role coverage and curve gaps)
- Similar hand detection (cluster by strategic roles, reuse prior evals)

