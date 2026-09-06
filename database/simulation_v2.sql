-- Durable simulation cache/control-plane schema for MagicView simulation v2.
-- Workers may run in GitHub Actions or on an explicitly registered local
-- machine. Neon stores experiment intent, leases, and immutable game results so
-- compatible games are never recomputed.
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
  -- Submitted decks are stored verbatim so a worker does not need to trust a
  -- path supplied by a scheduler. Existing named variants may leave this null.
  deck_text text,
  required_capabilities text[] not null default '{}',
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
  runner_id text,
  lease_token uuid,
  lease_expires_at timestamptz,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  last_error text,
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
create index if not exists idx_sim_shards_claim
  on sim_shards (status, lease_expires_at, created_at);

-- Add the local-runner fields when this file is applied to an installation
-- created from an earlier schema revision. This migration is deliberately not
-- executed by repository tooling; operators must review/apply it themselves.
alter table sim_variants add column if not exists deck_text text;
alter table sim_variants add column if not exists required_capabilities text[] not null default '{}';
alter table sim_shards add column if not exists runner_id text;
alter table sim_shards add column if not exists lease_token uuid;
alter table sim_shards add column if not exists lease_expires_at timestamptz;
alter table sim_shards add column if not exists attempt_count integer not null default 0;
alter table sim_shards add column if not exists last_error text;

alter table sim_experiments drop constraint if exists sim_experiments_status_check;
alter table sim_experiments add constraint sim_experiments_status_check
  check (status in ('queued','running','complete','failed','retired','promoted','needs_pilot'));

alter table sim_shards drop constraint if exists sim_shards_status_check;
alter table sim_shards add constraint sim_shards_status_check
  check (status in ('queued','running','complete','failed','cancelled','needs_pilot'));

-- Atomically claim one runnable shard. Expired running leases are eligible for
-- recovery; SKIP LOCKED permits more than one local worker without double
-- assignment. The returned row is the complete, immutable execution spec.
create or replace function claim_sim_shard(
  p_runner_id text,
  p_lease_seconds integer default 300
) returns table (
  shard_id uuid,
  lease_token uuid,
  experiment_id uuid,
  variant_id uuid,
  variant_code text,
  deck_sha256 text,
  deck_text text,
  required_capabilities text[],
  experiment_config jsonb,
  stage text,
  mode text,
  pod text,
  seat smallint,
  seed_start bigint,
  seed_end bigint,
  requested_games integer
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_shard_id uuid;
  v_token uuid := gen_random_uuid();
begin
  if nullif(btrim(p_runner_id), '') is null then
    raise exception 'runner id is required';
  end if;
  if p_lease_seconds < 60 or p_lease_seconds > 3600 then
    raise exception 'lease seconds must be between 60 and 3600';
  end if;

  select s.id into v_shard_id
  from sim_shards s
  join sim_experiments e on e.id = s.experiment_id
  where e.status in ('queued', 'running')
    and (
      s.status = 'queued'
      or (s.status = 'running' and s.lease_expires_at < timezone('utc', now()))
    )
  order by s.created_at, s.id
  for update of s skip locked
  limit 1;

  if v_shard_id is null then
    return;
  end if;

  update sim_shards s
  set status = 'running', runner_id = p_runner_id, lease_token = v_token,
      lease_expires_at = timezone('utc', now()) + make_interval(secs => p_lease_seconds),
      attempt_count = s.attempt_count + 1, last_error = null,
      updated_at = timezone('utc', now())
  where s.id = v_shard_id;

  update sim_experiments e set status = 'running', updated_at = timezone('utc', now())
  where e.id = (select s.experiment_id from sim_shards s where s.id = v_shard_id)
    and e.status = 'queued';

  return query
  select s.id, s.lease_token, s.experiment_id, s.variant_id, v.code,
         v.deck_sha256, v.deck_text, v.required_capabilities, e.config,
         s.stage, s.mode, s.pod, s.seat, s.seed_start, s.seed_end,
         s.requested_games
  from sim_shards s
  join sim_variants v on v.id = s.variant_id
  join sim_experiments e on e.id = s.experiment_id
  where s.id = v_shard_id;
end;
$$;

create or replace function renew_sim_shard_lease(
  p_shard_id uuid,
  p_lease_token uuid,
  p_lease_seconds integer default 300
) returns boolean
language sql
security definer
set search_path = public, pg_temp
as $$
  with renewed as (
    update sim_shards
    set lease_expires_at = timezone('utc', now()) + make_interval(secs => p_lease_seconds),
        updated_at = timezone('utc', now())
    where id = p_shard_id and lease_token = p_lease_token
      and status = 'running' and lease_expires_at >= timezone('utc', now())
    returning 1
  ) select exists(select 1 from renewed);
$$;

create or replace function finish_sim_shard(
  p_shard_id uuid,
  p_lease_token uuid,
  p_results jsonb
) returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_shard sim_shards%rowtype;
  v_variant sim_variants%rowtype;
  v_experiment sim_experiments%rowtype;
  v_item jsonb;
  v_count integer;
  v_distinct_count integer;
  v_seed bigint;
  v_cache_key text;
  v_game_id text;
  v_card jsonb;
begin
  select * into v_shard from sim_shards
  where id = p_shard_id for update;
  if not found or v_shard.status <> 'running'
     or v_shard.lease_token is distinct from p_lease_token
     or v_shard.lease_expires_at < timezone('utc', now()) then
    return false;
  end if;
  if jsonb_typeof(p_results) <> 'array' then
    raise exception 'results must be an array';
  end if;
  select count(*), count(distinct value->>'cacheKey')
    into v_count, v_distinct_count
  from jsonb_array_elements(p_results);
  if v_count <> v_shard.requested_games or v_distinct_count <> v_count then
    raise exception 'expected % distinct results, received % rows / % keys',
      v_shard.requested_games, v_count, v_distinct_count;
  end if;

  select * into strict v_variant from sim_variants where id = v_shard.variant_id;
  select * into strict v_experiment from sim_experiments where id = v_shard.experiment_id;

  for v_item in select value from jsonb_array_elements(p_results)
  loop
    v_seed := (v_item->>'seed')::bigint;
    v_cache_key := nullif(v_item->>'cacheKey', '');
    if v_cache_key is null
       or v_seed < v_shard.seed_start or v_seed > v_shard.seed_end
       or (v_item->>'kinnanSeat')::smallint <> v_shard.seat
       or v_item->>'variantDeckSha256' <> v_variant.deck_sha256
       or coalesce(v_item->>'mode', '') <> v_shard.mode
       or coalesce(v_item->>'pod', '') <> v_shard.pod
       or coalesce((v_item->>'telemetryV3Complete')::boolean, false) is not true
       or coalesce((v_item#>>'{cardTelemetryV3Coverage,valid}')::boolean, false) is not true
       or jsonb_array_length(coalesce(v_item->'cardTelemetryV3Rows', '[]'::jsonb)) <> 99
       or (
         select count(distinct card->>'registeredCardId')
         from jsonb_array_elements(coalesce(v_item->'cardTelemetryV3Rows', '[]'::jsonb)) as cards(card)
       ) <> 99 then
      raise exception 'result identity or telemetry does not match leased shard %', v_shard.id;
    end if;

    select min(card->>'gameId') into v_game_id
    from jsonb_array_elements(v_item->'cardTelemetryV3Rows') as cards(card);
    if nullif(v_game_id, '') is null or exists (
      select 1 from jsonb_array_elements(v_item->'cardTelemetryV3Rows') as cards(card)
      where card->>'gameId' <> v_game_id
        or card->>'deckHash' <> v_variant.deck_sha256
        or card->>'schemaVersion' <> 'kinnan-full99-card-telemetry-v3'
    ) then
      raise exception 'full-99 telemetry identity mismatch for shard %', v_shard.id;
    end if;

    insert into sim_game_results (
      cache_key, engine_id, pilot_version, optimizer_id, execution_profile,
      deck_sha256, pod_deck_sha256, seat_deck_sha256s, mode, pod, seed, seat,
      max_round, status, winner_seat, kinnan_won, first_assembly_turn,
      first_attempt_turn, deterministic_t4, certified_attempt,
      protected_attempt, strict_protected_t4, combo_line, failure_code,
      wall_ms, prompts, mulligans, opening_hand, kept_hand, observed_cards,
      observed_card_events, v2_positive_early_exit, v2_deadline_early_exit,
      audit
    ) values (
      v_cache_key, v_item->>'engineId', v_item->>'pilotVersion',
      v_item->>'optimizerId', v_item->>'executionProfile',
      v_item->>'variantDeckSha256', v_item->>'podDeckSha256',
      array(select jsonb_array_elements_text(coalesce(v_item->'seatDeckSha256s', '[]'::jsonb))),
      v_item->>'mode', v_item->>'pod', v_seed, (v_item->>'kinnanSeat')::smallint,
      coalesce((v_experiment.config->>'maxRound')::smallint, 4),
      v_item->>'status', nullif(v_item->>'winnerSeat', '')::smallint,
      coalesce((v_item->>'kinnanWon')::boolean, false),
      nullif(v_item->>'firstAssemblyTurn', '')::smallint,
      nullif(v_item->>'firstAttemptTurn', '')::smallint,
      coalesce((v_item->>'deterministicT4')::boolean, false),
      coalesce((v_item->>'certifiedDeterministicAttempt')::boolean, false),
      coalesce((v_item->>'protectedAttempt')::boolean, false),
      coalesce((v_item->>'strictProtectedT4')::boolean, false),
      v_item->>'comboLine', v_item->>'primaryFailureCode',
      nullif(v_item->>'wallMs', '')::integer,
      nullif(v_item->>'prompts', '')::integer,
      nullif(v_item->>'mulligans', '')::integer,
      coalesce(v_item->'openingHand', '[]'::jsonb),
      coalesce(v_item->'keptHand', '[]'::jsonb),
      array(select jsonb_array_elements_text(coalesce(v_item->'observedCards', '[]'::jsonb))),
      coalesce(v_item->'observedCardEvents', '[]'::jsonb),
      coalesce((v_item->>'v2EarlyExit')::boolean, false),
      coalesce((v_item->>'v2DeadlineExit')::boolean, false),
      jsonb_build_object(
        'cardTelemetryV3SchemaVersion', v_item->'cardTelemetryV3SchemaVersion',
        'cardTelemetryV3Coverage', v_item->'cardTelemetryV3Coverage',
        'rawActionTraceHash', v_item->'rawActionTraceHash',
        'rawActionTraceEventCount', v_item->'rawActionTraceEventCount'
      )
    ) on conflict (cache_key) do nothing;

    -- A cache-key collision is only reusable when its immutable identity is
    -- identical. Never silently link a result produced by another execution.
    if not exists (
      select 1 from sim_game_results g
      where g.cache_key = v_cache_key
        and g.engine_id = v_item->>'engineId'
        and g.pilot_version = v_item->>'pilotVersion'
        and g.optimizer_id = v_item->>'optimizerId'
        and g.execution_profile = v_item->>'executionProfile'
        and g.deck_sha256 = v_variant.deck_sha256
        and g.seed = v_seed and g.seat = v_shard.seat
        and g.mode = v_shard.mode and g.pod = v_shard.pod
    ) then
      raise exception 'cache key collision for %', v_cache_key;
    end if;

    insert into sim_game_action_traces_v3 (
      game_id, engine_id, deck_hash, variant, seed, seat, pod, horizon,
      pilot_version, schema_version, raw_action_trace, raw_action_trace_hash,
      raw_action_trace_event_count
    ) values (
      v_game_id, v_item->>'engineId', v_variant.deck_sha256,
      v_item->>'variant', v_seed, v_shard.seat, v_shard.pod,
      coalesce((v_experiment.config->>'maxRound')::integer, 4),
      v_item->>'pilotVersion', 'kinnan-full99-card-telemetry-v3',
      coalesce(v_item->'rawActionTrace', '[]'::jsonb),
      v_item->>'rawActionTraceHash',
      coalesce((v_item->>'rawActionTraceEventCount')::integer, 0)
    ) on conflict (game_id) do nothing;

    if not exists (
      select 1 from sim_game_action_traces_v3 t
      where t.game_id = v_game_id and t.engine_id = v_item->>'engineId'
        and t.deck_hash = v_variant.deck_sha256 and t.seed = v_seed
        and t.seat = v_shard.seat and t.pod = v_shard.pod
        and t.raw_action_trace_hash = v_item->>'rawActionTraceHash'
    ) then
      raise exception 'v3 game identity collision for %', v_game_id;
    end if;

    for v_card in select value from jsonb_array_elements(v_item->'cardTelemetryV3Rows')
    loop
      insert into sim_game_card_telemetry_v3 (
        game_id, registered_card_id, card_name, deck_hash, schema_version,
        seen, opening_hand, kept, mulliganed, first_seen_turn, first_drawn_turn,
        zone_changes, tutored, revealed, cast, played, mana_produced, mana_spent,
        activated, used, combo_participation, protection_participation,
        interaction_participation, attempt_present, protected_attempt_present,
        natural_win_presence, package_execution, outcome_role
      ) values (
        v_game_id, v_card->>'registeredCardId', v_card->>'cardName',
        v_variant.deck_sha256, v_card->>'schemaVersion',
        coalesce((v_card->>'seen')::boolean, false),
        coalesce((v_card->>'openingHand')::boolean, false),
        coalesce((v_card->>'kept')::boolean, false),
        coalesce((v_card->>'mulliganed')::boolean, false),
        nullif(v_card->>'firstSeenTurn', '')::integer,
        nullif(v_card->>'firstDrawnTurn', '')::integer,
        coalesce(v_card->'zoneChanges', '[]'::jsonb),
        coalesce((v_card->>'tutored')::boolean, false),
        coalesce((v_card->>'revealed')::boolean, false),
        coalesce((v_card->>'cast')::boolean, false),
        coalesce((v_card->>'played')::boolean, false),
        coalesce(v_card->'manaProduced', '{}'::jsonb),
        coalesce((v_card->>'manaSpent')::integer, 0),
        coalesce((v_card->>'activated')::boolean, false),
        coalesce((v_card->>'used')::boolean, false),
        coalesce((v_card->>'comboParticipation')::boolean, false),
        coalesce((v_card->>'protectionParticipation')::boolean, false),
        coalesce((v_card->>'interactionParticipation')::boolean, false),
        coalesce((v_card->>'attemptPresent')::boolean, false),
        coalesce((v_card->>'protectedAttemptPresent')::boolean, false),
        coalesce((v_card->>'naturalWinPresence')::boolean, false),
        coalesce((v_card->>'packageExecution')::boolean, false),
        v_card->>'outcomeRole'
      ) on conflict (game_id, registered_card_id) do nothing;
    end loop;

    if (select count(*) from sim_game_card_telemetry_v3 c where c.game_id = v_game_id) <> 99
       or exists (
         select 1
         from jsonb_array_elements(v_item->'cardTelemetryV3Rows') as cards(card)
         where not exists (
           select 1 from sim_game_card_telemetry_v3 c
           where c.game_id = v_game_id
             and c.registered_card_id = card->>'registeredCardId'
             and c.card_name = card->>'cardName'
             and c.deck_hash = v_variant.deck_sha256
         )
       ) then
      raise exception 'persisted full-99 coverage failed for game %', v_game_id;
    end if;

    insert into sim_experiment_games
      (experiment_id, variant_id, cache_key, stage, exposure_cards)
    values (
      v_shard.experiment_id, v_shard.variant_id, v_cache_key,
      v_shard.stage,
      array(select jsonb_array_elements_text(coalesce(v_item->'exposureCards', '[]'::jsonb)))
    ) on conflict do nothing;
  end loop;

  update sim_shards
  set status = 'complete', completed_games = v_count,
      lease_token = null, lease_expires_at = null, updated_at = timezone('utc', now())
  where id = v_shard.id;

  if not exists (
    select 1 from sim_shards s
    where s.experiment_id = v_shard.experiment_id
      and s.status not in ('complete', 'cancelled')
  ) then
    update sim_experiments
    set status = 'complete', updated_at = timezone('utc', now())
    where id = v_shard.experiment_id;
  end if;
  return true;
end;
$$;

create or replace function fail_sim_shard(
  p_shard_id uuid,
  p_lease_token uuid,
  p_error text,
  p_needs_pilot boolean default false
) returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_experiment_id uuid;
begin
  update sim_shards
  set status = case when p_needs_pilot then 'needs_pilot' else 'failed' end,
      last_error = left(coalesce(p_error, 'unspecified worker failure'), 8000),
      lease_token = null, lease_expires_at = null,
      updated_at = timezone('utc', now())
  where id = p_shard_id and lease_token = p_lease_token and status = 'running'
  returning experiment_id into v_experiment_id;
  if v_experiment_id is null then
    return false;
  end if;
  update sim_experiments
  set status = case when p_needs_pilot then 'needs_pilot' else 'failed' end,
      updated_at = timezone('utc', now())
  where id = v_experiment_id;
  return true;
end;
$$;

-- SECURITY DEFINER RPCs are not callable until an operator grants them to the
-- dedicated Data API worker role. Do not grant these to anon/authenticated.
revoke all on function claim_sim_shard(text, integer) from public;
revoke all on function renew_sim_shard_lease(uuid, uuid, integer) from public;
revoke all on function finish_sim_shard(uuid, uuid, jsonb) from public;
revoke all on function fail_sim_shard(uuid, uuid, text, boolean) from public;
