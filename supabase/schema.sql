create extension if not exists "pgcrypto";

create table if not exists public.users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null unique,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.decks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users (id) on delete cascade,
  name text not null,
  commander text not null,
  bracket integer not null check (bracket between 1 and 5),
  strategy_summary text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.deck_cards (
  id uuid primary key default gen_random_uuid(),
  deck_id uuid not null references public.decks (id) on delete cascade,
  card_name text not null,
  quantity integer not null check (quantity > 0)
);

create table if not exists public.cards (
  name text primary key,
  name_normalized text not null unique,
  scryfall_id text unique,
  mana_value numeric,
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

create table if not exists public.game_sessions (
  id uuid primary key default gen_random_uuid(),
  deck_id uuid not null references public.decks (id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.hand_snapshots (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.game_sessions (id) on delete cascade,
  mulligan_number integer not null default 0 check (mulligan_number >= 0),
  seat_position text not null default 'first' check (seat_position in ('first', 'middle', 'last')),
  cards jsonb not null,
  decision text not null check (decision in ('KEEP', 'MULLIGAN')),
  confidence numeric(4, 3) not null check (confidence >= 0 and confidence <= 1),
  reasoning text[] not null default '{}',
  turn_plan jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists set_decks_updated_at on public.decks;
create trigger set_decks_updated_at
before update on public.decks
for each row
execute procedure public.set_updated_at();

drop trigger if exists set_cards_updated_at on public.cards;
create trigger set_cards_updated_at
before update on public.cards
for each row
execute procedure public.set_updated_at();

create or replace function public.handle_auth_user_sync()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (id, email)
  values (new.id, new.email)
  on conflict (id) do update
    set email = excluded.email;
  return new;
end;
$$;

drop trigger if exists on_auth_user_sync on auth.users;
create trigger on_auth_user_sync
after insert or update of email on auth.users
for each row
execute procedure public.handle_auth_user_sync();

alter table public.users enable row level security;
alter table public.decks enable row level security;
alter table public.deck_cards enable row level security;
alter table public.cards enable row level security;
alter table public.game_sessions enable row level security;
alter table public.hand_snapshots enable row level security;

drop policy if exists "Users can read their own profile" on public.users;
create policy "Users can read their own profile"
on public.users
for select
to authenticated
using (auth.uid() = id);

drop policy if exists "Users can update their own profile" on public.users;
create policy "Users can update their own profile"
on public.users
for update
to authenticated
using (auth.uid() = id)
with check (auth.uid() = id);

drop policy if exists "Users can insert their own profile" on public.users;
create policy "Users can insert their own profile"
on public.users
for insert
to authenticated
with check (auth.uid() = id);

drop policy if exists "Users manage their decks" on public.decks;
create policy "Users manage their decks"
on public.decks
for all
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users manage deck cards through owned decks" on public.deck_cards;
create policy "Users manage deck cards through owned decks"
on public.deck_cards
for all
to authenticated
using (
  exists (
    select 1
    from public.decks
    where decks.id = deck_cards.deck_id
      and decks.user_id = auth.uid()
  )
)
with check (
  exists (
    select 1
    from public.decks
    where decks.id = deck_cards.deck_id
      and decks.user_id = auth.uid()
  )
);

drop policy if exists "Authenticated users can read cached cards" on public.cards;
create policy "Authenticated users can read cached cards"
on public.cards
for select
to authenticated
using (true);

drop policy if exists "Users manage sessions through owned decks" on public.game_sessions;
create policy "Users manage sessions through owned decks"
on public.game_sessions
for all
to authenticated
using (
  exists (
    select 1
    from public.decks
    where decks.id = game_sessions.deck_id
      and decks.user_id = auth.uid()
  )
)
with check (
  exists (
    select 1
    from public.decks
    where decks.id = game_sessions.deck_id
      and decks.user_id = auth.uid()
  )
);

drop policy if exists "Users manage hand snapshots through owned sessions" on public.hand_snapshots;
create policy "Users manage hand snapshots through owned sessions"
on public.hand_snapshots
for all
to authenticated
using (
  exists (
    select 1
    from public.game_sessions
    join public.decks on decks.id = game_sessions.deck_id
    where game_sessions.id = hand_snapshots.session_id
      and decks.user_id = auth.uid()
  )
)
with check (
  exists (
    select 1
    from public.game_sessions
    join public.decks on decks.id = game_sessions.deck_id
    where game_sessions.id = hand_snapshots.session_id
      and decks.user_id = auth.uid()
  )
);

insert into storage.buckets (id, name, public)
values ('hand-images', 'hand-images', false)
on conflict (id) do nothing;

drop policy if exists "Users can upload their own hand images" on storage.objects;
create policy "Users can upload their own hand images"
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'hand-images'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "Users can read their own hand images" on storage.objects;
create policy "Users can read their own hand images"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'hand-images'
  and (storage.foldername(name))[1] = auth.uid()::text
);

