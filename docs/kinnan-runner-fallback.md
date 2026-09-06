# Kinnan local-primary / GitHub-fallback runner

The local workstation is the primary simulation worker. GitHub Actions is a fallback worker only; it does not own a separate simulation path.

## Invariants

- Both workers execute `engine-tests/local_queue_runner_safe.py`.
- The safe wrapper exits before any Neon call when the policy manifest has `rankingReady=false`.
- Actual simulation still lives only in `engine-tests/local_queue_runner.py`, which invokes `run_kinnan_sim.py --purpose ranking`.
- Both workers claim work through the same Neon `claim_sim_shard` lease protocol. An expired lease can be recovered; an unexpired lease cannot be stolen.
- The GitHub workflow never starts Forge merely because a workflow is scheduled. It first requires `rankingReady=true` and `sim_fallback_eligible(...) = true`.
- `sim_fallback_eligible` is read-only. It returns true only when eligible queue work exists and no healthy local heartbeat has been observed within the stale threshold.

## Database setup

Apply these repository migrations in order using a direct, reviewed database connection:

1. `engine-tests/full99_neon_schema_v3.sql`
2. `database/simulation_v2.sql`
3. `database/simulation_runner_fallback.sql`

Grant the dedicated worker role the four queue RPCs documented in `docs/local-kinnan-runner.md`, plus:

```sql
grant execute on function touch_sim_runner_heartbeat(text,text,text,text,text,text,boolean,uuid) to sim_worker;
grant execute on function sim_fallback_eligible(integer) to sim_worker;
```

Do not grant these RPCs to the anonymous/application role.

## Local scheduling

Continue to schedule:

```powershell
pwsh.exe -NoProfile -File C:\path\to\magicview\scripts\run-local-kinnan-queue.ps1 -UseWsl -MaxShards 4
```

The PowerShell launcher now uses the safe wrapper and sets `KINNAN_RUNNER_KIND=local`.

When `rankingReady=false`, a normal scheduled invocation exits with `claimed=0` and `databaseCalls=0`. `-DryRun` still delegates to the canonical component preflight so an operator can validate the machine without claiming queue work.

## GitHub fallback

`.github/workflows/kinnan-local-runner-fallback.yml` runs every 15 minutes. It needs repository secrets:

- `NEON_DATA_API`
- `NEON_DATA_API_TOKEN`
- `MANABREW_REF`

The workflow checks the checked-out manifest first. If ranking is blocked it exits without touching Neon. If ranking is enabled, it calls `sim_fallback_eligible(1200)`. Only when the local heartbeat has been stale for 20 minutes and eligible work exists does it build the pinned Forge runtime and run one leased shard.

The fallback worker identifies itself as `github-${GITHUB_RUN_ID}` and sets `KINNAN_RUNNER_KIND=github`.

## Failure behavior

If the local machine dies during a shard, its shard lease eventually expires. The GitHub fallback can recover that shard only through `claim_sim_shard`; the old local lease token cannot publish results afterward. If the local machine is healthy, its periodic runner heartbeat suppresses fallback compute.
