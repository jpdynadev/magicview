-- Runner-health coordination for local-primary / GitHub-fallback Kinnan compute.
-- Additive migration only: it does not create, claim, reclassify, or drain work.

create table if not exists sim_runner_heartbeats (
  runner_id text primary key,
  runner_kind text not null check (runner_kind in ('local','github')),
  status text not null check (status in ('active','idle','error')),
  repo_sha text,
  engine_id text,
  manifest_sha256 text,
  ranking_ready boolean not null default false,
  current_shard uuid references sim_shards(id) on delete set null,
  last_seen_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_sim_runner_heartbeats_kind_seen
  on sim_runner_heartbeats (runner_kind, last_seen_at desc);

create or replace function touch_sim_runner_heartbeat(
  p_runner_id text,
  p_runner_kind text,
  p_status text,
  p_repo_sha text,
  p_engine_id text,
  p_manifest_sha256 text,
  p_ranking_ready boolean,
  p_current_shard uuid default null
) returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if nullif(btrim(p_runner_id), '') is null then
    raise exception 'runner id is required';
  end if;
  if p_runner_kind not in ('local','github') then
    raise exception 'runner kind must be local or github';
  end if;
  if p_status not in ('active','idle','error') then
    raise exception 'runner status must be active, idle, or error';
  end if;

  insert into sim_runner_heartbeats (
    runner_id, runner_kind, status, repo_sha, engine_id,
    manifest_sha256, ranking_ready, current_shard,
    last_seen_at, updated_at
  ) values (
    p_runner_id, p_runner_kind, p_status, nullif(p_repo_sha, ''),
    nullif(p_engine_id, ''), nullif(p_manifest_sha256, ''),
    p_ranking_ready, p_current_shard,
    timezone('utc', now()), timezone('utc', now())
  )
  on conflict (runner_id) do update set
    runner_kind = excluded.runner_kind,
    status = excluded.status,
    repo_sha = excluded.repo_sha,
    engine_id = excluded.engine_id,
    manifest_sha256 = excluded.manifest_sha256,
    ranking_ready = excluded.ranking_ready,
    current_shard = excluded.current_shard,
    last_seen_at = timezone('utc', now()),
    updated_at = timezone('utc', now());

  return true;
end;
$$;

-- Read-only fallback decision. GitHub may start compute only when:
--   1. eligible queued work exists, and
--   2. no local runner heartbeat is fresh within the configured threshold.
-- Expired shard leases remain governed solely by claim_sim_shard; this function
-- never claims or modifies a shard.
create or replace function sim_fallback_eligible(
  p_stale_seconds integer default 1200
) returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_has_work boolean;
  v_local_fresh boolean;
begin
  if p_stale_seconds < 60 or p_stale_seconds > 86400 then
    raise exception 'stale seconds must be between 60 and 86400';
  end if;

  select exists (
    select 1
    from sim_shards s
    join sim_experiments e on e.id = s.experiment_id
    where e.status in ('queued','running')
      and (
        s.status = 'queued'
        or (
          s.status = 'running'
          and s.lease_expires_at < timezone('utc', now())
        )
      )
  ) into v_has_work;

  select exists (
    select 1
    from sim_runner_heartbeats h
    where h.runner_kind = 'local'
      and h.status in ('active','idle')
      and h.ranking_ready is true
      and h.last_seen_at >= timezone('utc', now()) - make_interval(secs => p_stale_seconds)
  ) into v_local_fresh;

  return v_has_work and not v_local_fresh;
end;
$$;

revoke all on function touch_sim_runner_heartbeat(text,text,text,text,text,text,boolean,uuid) from public;
revoke all on function sim_fallback_eligible(integer) from public;

-- Grant only to the dedicated worker role after review/application:
-- grant execute on function touch_sim_runner_heartbeat(text,text,text,text,text,text,boolean,uuid) to sim_worker;
-- grant execute on function sim_fallback_eligible(integer) to sim_worker;
