# Local Kinnan queue runner

The scheduled ChatGPT task remains the control plane: it validates new deck
submissions and creates `sim_experiments`, `sim_variants`, and `sim_shards` rows.
`engine-tests/local_queue_runner.py` replaces GitHub-hosted Actions compute. A
local invocation leases one or more queued shards, runs the repository's
semantic gates and canonical launcher, and transactionally publishes complete
full-99 v3 results to Neon.

## Safety and queue semantics

- `claim_sim_shard` uses `FOR UPDATE SKIP LOCKED` and also recovers expired
  leases. A unique lease token fences stale workers.
- A heartbeat renews the lease while Forge runs. A worker that loses its lease
  terminates Forge and does not ingest.
- `finish_sim_shard` inserts immutable results and links them to the experiment
  in one transaction. Primary keys make retries idempotent, while identity
  comparisons reject cache-key collisions.
- Submitted text must contain exactly one Kinnan commander and 99 unique main
  cards, and its SHA-256 must equal `sim_variants.deck_sha256`.
- The queue row declares `required_capabilities`. Unknown or non-production
  capabilities, or a manifest with `rankingReady=false`, move the shard and
  experiment to `needs_pilot`; they never run through a legacy pilot.
- The local runner always executes `run_kinnan_sim.py --purpose ranking`. It
  cannot bypass the repository's policy-parity and live-runner gates.

## One-time database setup

Review and apply `engine-tests/full99_neon_schema_v3.sql` and then
`database/simulation_v2.sql` using a direct, unpooled database connection. The
repository does not apply either file automatically. The latter file revokes
all four worker RPCs from `public`; grant only these signatures to the dedicated
Data API role represented by the local token:

```sql
grant execute on function claim_sim_shard(text, integer) to sim_worker;
grant execute on function renew_sim_shard_lease(uuid, uuid, integer) to sim_worker;
grant execute on function finish_sim_shard(uuid, uuid, jsonb) to sim_worker;
grant execute on function fail_sim_shard(uuid, uuid, text, boolean) to sim_worker;
```

Do not use the `anon` or normal application role. Rotate the worker credential
if it is ever written to a log or committed.

## Runtime configuration

Build the pinned Manabrew/Forge runtime using Java 21, Node 22, Maven, and the
same `MANABREW_REF` used by the experiment. Apply
`engine-tests/apply_manabrew_repairs.py` before running Manabrew's
`node scripts/harness.mjs build`. Set these machine-level environment variables:

```text
NEON_DATA_API=https://<endpoint>/rest/v1
NEON_DATA_API_TOKEN=<dedicated worker JWT>
MANABREW_REF=<pinned commit>
MANABREW_HARNESS_JAR=C:\path\to\forge-harness-jar-with-dependencies.jar
MANABREW_FORGE_HOME=C:\path\to\forge\forge-gui
```

No database URL or token has a fallback in the runner.

## Run and schedule

From PowerShell:

```powershell
.\scripts\run-local-kinnan-queue.ps1 -DryRun
.\scripts\run-local-kinnan-queue.ps1 -MaxShards 1
```

Dry-run mode executes the semantic suite and canonical component canary, prints
which environment variables are configured plus the current `rankingReady`
value, and makes zero database calls.

Windows Task Scheduler can run `pwsh.exe` with:

```text
-NoProfile -File C:\path\to\magicview\scripts\run-local-kinnan-queue.ps1 -MaxShards 4
```

Use a dedicated Windows account, set “Do not start a new instance” for overlap,
and store secrets as account-level environment variables rather than task
arguments. The machine must be awake; expired leases make interrupted shards
recoverable on the next invocation.
