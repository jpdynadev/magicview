create extension if not exists "pgcrypto";

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  password_hash text not null,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists decks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  name text not null,
  commander text not null,
  bracket integer not null check (bracket between 1 and 5),
  strategy_summary text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists deck_cards (
  id uuid primary key default gen_random_uuid(),
  deck_id uuid not null references decks (id) on delete cascade,
  card_name text not null,
  quantity integer not null check (quantity > 0)
);

create table if not exists cards (
  name text primary key,
  name_normalized text not null unique,
  scryfall_id text unique,
  mana_value double precision,
  type_line text,
  oracle_text text,
  colors text[] not null default '{}',
  tags jsonb not null default '[]'::jsonb,
  compact_summary text,
  primary_abilities text[] not null default '{}',
  secondary_abilities text[] not null default '{}',
  mulligan_relevance_score integer check (mulligan_relevance_score between 1 and 10),
  image_uri text,
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists game_sessions (
  id uuid primary key default gen_random_uuid(),
  deck_id uuid not null references decks (id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists hand_snapshots (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references game_sessions (id) on delete cascade,
  mulligan_number integer not null default 0 check (mulligan_number >= 0),
  seat_position text not null default 'first' check (seat_position in ('first', 'middle', 'last')),
  cards jsonb not null,
  decision text not null check (decision in ('KEEP', 'MULLIGAN')),
  confidence double precision not null check (confidence >= 0 and confidence <= 1),
  reasoning text[] not null default '{}',
  turn_plan jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_decks_user_id on decks (user_id);
create index if not exists idx_deck_cards_deck_id on deck_cards (deck_id);
create index if not exists idx_game_sessions_deck_id on game_sessions (deck_id);
create index if not exists idx_hand_snapshots_session_id on hand_snapshots (session_id);
create index if not exists idx_cards_name_normalized on cards (name_normalized);

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists set_decks_updated_at on decks;
create trigger set_decks_updated_at
before update on decks
for each row
execute procedure set_updated_at();

drop trigger if exists set_cards_updated_at on cards;
create trigger set_cards_updated_at
before update on cards
for each row
execute procedure set_updated_at();
