create schema if not exists cedh;

create table if not exists cedh.full99_telemetry_runs (
  run_key text primary key,
  source_run_id bigint,
  artifact_name text not null,
  schema_version text not null,
  valid_games integer not null,
  expected_rows integer not null,
  actual_rows integer not null,
  games_with_exactly_99 integer not null,
  missing_cards jsonb not null default '{}'::jsonb,
  duplicate_rows integer not null default 0,
  telemetry_complete boolean not null default false,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists cedh.full99_game_card_telemetry (
  run_key text not null references cedh.full99_telemetry_runs(run_key) on delete cascade,
  schema_version text not null,
  deck_hash text not null,
  variant text not null,
  canonical_key text not null,
  seed bigint not null,
  seat integer not null,
  pod text not null,
  card_identity text not null,
  present boolean not null default true,
  opening_hand boolean not null default false,
  kept boolean not null default false,
  mulliganed boolean not null default false,
  put_back boolean not null default false,
  seen boolean not null default false,
  first_seen_turn integer,
  drawn boolean not null default false,
  first_drawn_turn integer,
  zones_by_turn jsonb not null default '[]'::jsonb,
  zone_changes jsonb not null default '[]'::jsonb,
  tutored boolean not null default false,
  revealed boolean not null default false,
  cast_or_played boolean not null default false,
  cast_or_played_turns jsonb not null default '[]'::jsonb,
  mana_produced boolean not null default false,
  mana_spent boolean not null default false,
  mana_pool_before_actions jsonb not null default '[]'::jsonb,
  activated boolean not null default false,
  used boolean not null default false,
  combo_participation boolean not null default false,
  protection_participation boolean not null default false,
  interaction_participation boolean not null default false,
  outcome_attribution jsonb not null default '{}'::jsonb,
  assembly_t4 boolean not null default false,
  attempt_t4 boolean not null default false,
  protected_attempt_t4 boolean not null default false,
  natural_win boolean not null default false,
  package_execution boolean not null default false,
  failure_code text,
  primary key (run_key, canonical_key, card_identity)
);

create index if not exists full99_card_run_variant_idx on cedh.full99_game_card_telemetry(run_key, variant);
create index if not exists full99_card_identity_idx on cedh.full99_game_card_telemetry(card_identity);
create index if not exists full99_card_outcomes_idx on cedh.full99_game_card_telemetry(run_key, protected_attempt_t4, natural_win);

create or replace view cedh.full99_card_metrics as
select
  run_key,
  variant,
  deck_hash,
  card_identity,
  count(*) as games,
  count(*) filter (where seen) as seen_games,
  count(*) filter (where opening_hand) as opening_hand_games,
  count(*) filter (where cast_or_played) as cast_or_played_games,
  count(*) filter (where combo_participation) as combo_games,
  count(*) filter (where protection_participation) as protection_games,
  count(*) filter (where interaction_participation) as interaction_games,
  count(*) filter (where attempt_t4) as attempt_presence_games,
  count(*) filter (where protected_attempt_t4) as protected_attempt_presence_games,
  count(*) filter (where natural_win) as natural_win_presence_games,
  count(*) filter (where package_execution) as package_execution_games
from cedh.full99_game_card_telemetry
group by run_key, variant, deck_hash, card_identity;
