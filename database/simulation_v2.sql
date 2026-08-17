-- Durable simulation cache/control-plane schema for MagicView simulation v2.
-- GitHub Actions remains the compute layer; Neon stores experiment intent and
-- immutable game results so compatible games are never recomputed.
--
-- Deliberately no trigger functions: workers/control-plane update updated_at
-- explicitly, which keeps this migration simple and portable.

create table if not exists sim_experiments (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  experiment_class text not null check (experiment_class in ('architecture','package','singleton')),
  baseline_variant text not null default 'P00_F10',
  status text not null default 'queued' check (status in ('queued','running','complete','failed','retired','promoted')),
  primary_endpoint text not null default 'strict_protected_t4',
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists sim_variants (
  id uuid primary key default gen_random_uuid(),
  experiment_id uuid not null references sim_experiments(id) on delete cascade,
  code text not null,
  deck_name text,
  deck_sha256 text not null,
  parent_code text,
  mutation jsonb not null default '{}'::jsonb,
  exposure_cards text[] not null default '{}',
  created_at timestamptz not null default timezone('utc', now()),
  unique (experiment_id, code)
);

create table if not exists sim_game_results (
  cache_key text primary key,
  engine_id text not null,
  pilot_version text not null,
  optimizer_id text not null,
  execution_profile text not null,
  deck_sha256 text not null,
  pod_deck_sha256 text not null,
  seat_deck_sha256s text[] not null default '{}',
  mode text not null check (mode in ('screen','adversarial')),
  pod text not null,
  seed bigint not null,
  seat smallint not null check (seat between 0 and 3),
  max_round smallint not null,
  status text not null,
  winner_seat smallint,
  kinnan_won boolean not null default false,
  first_assembly_turn smallint,
  first_attempt_turn smallint,
  deterministic_t4 boolean not null default false,
  certified_attempt boolean not null default false,
  protected_attempt boolean not null default false,
  strict_protected_t4 boolean not null default false,
  combo_line text,
  failure_code text,
  wall_ms integer,
  prompts integer,
  mulligans integer,
  opening_hand jsonb not null default '[]'::jsonb,
  kept_hand jsonb not null default '[]'::jsonb,
  observed_cards text[] not null default '{}',
  observed_card_events jsonb not null default '[]'::jsonb,
  v2_positive_early_exit boolean not null default false,
  v2_deadline_early_exit boolean not null default false,
  audit jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists sim_experiment_games (
  experiment_id uuid not null references sim_experiments(id) on delete cascade,
  variant_id uuid not null references sim_variants(id) on delete cascade,
  cache_key text not null references sim_game_results(cache_key) on delete restrict,
  stage text not null check (stage in ('screen','confirm','deep','exposure')),
  exposure_cards text[] not null default '{}',
  created_at timestamptz not null default timezone('utc', now()),
  primary key (experiment_id, variant_id, cache_key, stage)
);

create table if not exists sim_shards (
  id uuid primary key default gen_random_uuid(),
  experiment_id uuid not null references sim_experiments(id) on delete cascade,
  variant_id uuid not null references sim_variants(id) on delete cascade,
  stage text not null check (stage in ('screen','confirm','deep','exposure')),
  mode text not null check (mode in ('screen','adversarial')),
  pod text not null,
  seat smallint not null check (seat between 0 and 3),
  seed_start bigint not null,
  seed_end bigint not null check (seed_end >= seed_start),
  requested_games integer not null check (requested_games > 0),
  completed_games integer not null default 0 check (completed_games >= 0),
  cache_hits integer not null default 0 check (cache_hits >= 0),
  jvm_starts integer not null default 0 check (jvm_starts >= 0),
  wall_ms bigint,
  status text not null default 'queued' check (status in ('queued','running','complete','failed','cancelled')),
  github_run_id bigint,
  github_job_id bigint,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (experiment_id, variant_id, stage, pod, seat, seed_start, seed_end)
);

create index if not exists idx_sim_results_lookup
  on sim_game_results (engine_id, pilot_version, optimizer_id, execution_profile, deck_sha256, pod_deck_sha256, mode, pod, seat, seed, max_round);
create index if not exists idx_sim_results_deck
  on sim_game_results (deck_sha256, pod_deck_sha256, mode, pod, seat);
create index if not exists idx_sim_results_pt4
  on sim_game_results (strict_protected_t4) where strict_protected_t4 = true;
create index if not exists idx_sim_results_observed_cards
  on sim_game_results using gin (observed_cards);
create index if not exists idx_sim_experiment_games_exp
  on sim_experiment_games (experiment_id, variant_id, stage);
create index if not exists idx_sim_shards_exp_status
  on sim_shards (experiment_id, status);
