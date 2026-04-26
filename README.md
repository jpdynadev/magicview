# MagicView

MagicView is a deployable MVP for Magic: The Gathering Commander players. It lets a user sign up, import a deck, start a game session, paste a 7-card opening hand, and receive a structured AI mulligan recommendation with confidence, reasoning, and a 3-turn plan.

## Stack

- Frontend: Next.js App Router
- Backend: Netlify Functions
- Database/Auth/Storage: Supabase
- Card data: Scryfall bulk data + named card API fallback
- AI: OpenAI Responses API with structured JSON output

## MVP Features

- Email/password signup and login through Supabase Auth
- Dashboard for deck creation and deck history
- Commander deck import by pasted list
- Commander selection and bracket selection (1-5)
- Game session creation
- Opening-hand analysis for exactly 7 cards
- Saved hand snapshots with keep/mulligan decision, confidence, reasoning, and turn plan
- Cached Scryfall cards with deterministic tags and optional AI compression

## Important Folders

```text
magicview/
├─ netlify/
│  └─ functions/
│     ├─ analyze-hand.ts
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
│  │  └─ page.tsx
│  ├─ components/
│  │  ├─ auth/
│  │  ├─ dashboard/
│  │  ├─ decks/
│  │  ├─ layout/
│  │  └─ session/
│  └─ lib/
│     ├─ api.ts
│     ├─ auth-context.tsx
│     ├─ card-tags.ts
│     ├─ decklist.ts
│     ├─ env.ts
│     ├─ supabase-browser.ts
│     ├─ types.ts
│     └─ server/
│        ├─ ai-schemas.ts
│        ├─ card-cache.ts
│        ├─ deck-strategy.ts
│        ├─ hand-analysis.ts
│        ├─ netlify.ts
│        ├─ openai-structured.ts
│        ├─ openai.ts
│        └─ supabase-admin.ts
├─ supabase/
│  └─ schema.sql
├─ .env.example
├─ netlify.toml
├─ next.config.ts
└─ package.json
```

## Database Schema

The full schema is in [`supabase/schema.sql`](./supabase/schema.sql).

It creates:

- `public.users`
- `public.decks`
- `public.deck_cards`
- `public.cards`
- `public.game_sessions`
- `public.hand_snapshots`

It also includes:

- auth user sync trigger from `auth.users` to `public.users`
- row-level security policies for every player-owned table
- a `hand-images` Supabase Storage bucket for future hand image uploads

## Card Data Pipeline

### Runtime behavior

Deck import and hand analysis both call `ensureCardsCached()`.

If a card is missing from the local `cards` cache:

1. MagicView hits the Scryfall named-card API
2. It deterministically tags the card
3. It generates a fallback summary
4. It optionally compresses the card with OpenAI
5. It upserts the result into `public.cards`

This means the MVP still works even before a full bulk sync is run.

### Bulk ingest script

Run the bulk ingest script when you want to preload the cache:

```bash
npm run scryfall:sync -- --download
```

Useful variants:

```bash
# Download + ingest first 500 cards with deterministic tags only
npm run scryfall:sync -- --download --limit 500

# Ingest from existing file and run AI compression
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

The AI response is forced through a strict JSON schema:

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

### `upsert-deck`

- Verifies Supabase auth token
- Parses the pasted decklist
- Caches missing cards from Scryfall
- Builds a deck strategy summary
- Inserts or updates the deck and its card list

### `start-session`

- Verifies deck ownership
- Creates a new `game_sessions` row

### `analyze-hand`

- Verifies session ownership
- Resolves all 7 hand cards plus commander(s)
- Builds the compact AI payload
- Calls OpenAI with structured output
- Persists the result into `hand_snapshots`

## Local Setup

1. Create a Supabase project.
2. Run [`supabase/schema.sql`](./supabase/schema.sql) in the Supabase SQL editor.
3. Copy `.env.example` to `.env.local`.
4. Fill in:

```bash
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
OPENAI_API_KEY=...
OPENAI_MULLIGAN_MODEL=gpt-5.4-mini
OPENAI_CARD_COMPRESSION_MODEL=gpt-5.4-nano
SUPABASE_HAND_IMAGES_BUCKET=hand-images
```

5. Install dependencies:

```bash
npm install
```

6. Start local development:

```bash
npm run dev
```

7. Optional: run through Netlify’s local runtime:

```bash
npx netlify dev
```

## Example API Calls

These examples assume you already have a Supabase access token from a signed-in user.

### Create or import a deck

```bash
curl -X POST http://localhost:8888/.netlify/functions/upsert-deck \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SUPABASE_ACCESS_TOKEN" \
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
  -H "Authorization: Bearer YOUR_SUPABASE_ACCESS_TOKEN" \
  -d '{
    "deckId": "YOUR_DECK_UUID"
  }'
```

### Analyze an opening hand

```bash
curl -X POST http://localhost:8888/.netlify/functions/analyze-hand \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SUPABASE_ACCESS_TOKEN" \
  -d '{
    "sessionId": "YOUR_SESSION_UUID",
    "openingHandText": "Command Tower\nIsland\nSol Ring\nArcane Signet\nRhystic Study\nSwords to Plowshares\nSmothering Tithe",
    "mulliganNumber": 0,
    "seatPosition": "first"
  }'
```

## Netlify Deployment

The repository already has:

- `netlify.toml`
- Next.js production build config
- a dedicated `netlify/functions` directory

### Deploy steps

1. Push this repository to GitHub.
2. In Netlify, create or link a site to this repo.
3. Add the environment variables from `.env.example` in Netlify Site Settings.
4. Deploy with either:

```bash
npx netlify deploy --build
```

For production:

```bash
npx netlify deploy --build --prod
```

### Current CLI status

- Netlify CLI is authenticated in this environment.
- This repository is **not yet linked** to a Netlify site.
- `npx netlify link --git-remote-url https://github.com/jpdynadev/magicview.git` returned **no matching project found**.

That means the code is deployable now, but an actual Netlify site still needs to be created or linked before a real deploy can happen.

## Verification

The current repository passes:

```bash
npm run typecheck
npm run build
```

## Post-MVP Roadmap

### 1. Image recognition for hands

- Upload opening hand photos to Supabase Storage
- Use OCR + card matching against Scryfall
- Reuse the existing `analyze-hand` pipeline

### 2. Opponent tracking

- Add pod metadata, commanders seen, and pace indicators
- Let mulligan logic adapt to table speed and interaction density

### 3. Game outcome learning

- Track whether the kept hand won, lost, or stalled
- Build feedback loops for prompt/eval improvement

### 4. Deck optimization suggestions

- Surface repeated weak keep patterns
- Suggest cuts/adds by comparing weak hands with deck tags and curve signals

### 5. Similar hand detection

- Hash saved hands and cluster by card role rather than exact card names
- Reuse prior evaluations to reduce cost and improve consistency
