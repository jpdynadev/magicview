# MagicView Simulation v2

## Why this exists

The legacy Kinnan benchmark loop was statistically useful but computationally
wasteful:

1. one fresh `java -Xmx4g` Forge process per game;
2. full trace materialization and JSON writes for every game;
3. fixed sample sizes even when a mutation was obviously losing;
4. repeated recomputation of the F10 baseline;
5. large 50-game shards that load-balance poorly when a few games time out;
6. singleton tests reported deck-level rates without measuring whether the
   changed slot was actually exposed.

Simulation v2 keeps Forge/Manabrew as the rules authority and keeps GitHub
Actions as compute. It changes orchestration and measurement, not Magic rules.

## v2 compute model

### Persistent JVM micro-batching

`sim_v2_worker.py` wraps the proven v8 pilot and lends it a persistent Forge JVM.
The pilot still believes it owns a process, but lifecycle calls are proxied. The
pool restarts the real JVM every N games (default 6) to bound session/memory
growth.

Default heap is `-Xms256m -Xmx1536m` rather than `-Xmx4g`.

Before this becomes the default, `kinnan-sim-v2-smoke.yml` compares seeded
outcomes with `jvm_reuse=1` versus persistent reuse. Any mismatch in status,
assembly turn, attempt turn, strict protected-T4 result, win, or failure code
fails the smoke test.

### Canonical seed banks

The production workflow uses fixed seed banks. This is deliberate.

A cached F10 result is reusable for a new candidate if all of these match:

- Manabrew/Forge engine ID
- pilot version/code hash
- deck hash
- pod
- seat
- seed
- observation horizon

The worker records a deterministic SHA-256 cache key for every game.

GitHub Actions cache currently gives us rerun/canonical-shard reuse. The long-term
store should be Neon so baseline games are reusable across workflows without
depending on Actions cache retention.

### Small shards

Each worker handles 25 games. This improves load balancing and makes retries
cheap. A pathological timeout burns one small shard rather than holding a
50-100 game job hostage.

### Adaptive compute

Screening is rejection-oriented, not confirmation-oriented.

Default v2 flow:

1. 25 games x 4 fixed seats = 100 paired screen games per candidate.
2. `sim_v2_rank.py` computes paired exact McNemar statistics and practical
   domination.
3. Obvious losers are rejected without adversarial confirmation.
4. Only the best survivor gets the expensive pod matrix.
5. Confirmation uses 25-game shards across 4 pods x 4 seats x 4 shards =
   1,600 games per confirmed deck.

For subtle singleton effects, this should later be extended to a sequential deep
stage (2k -> 5k+) only while the result remains decision-relevant.

## Statistical model

Primary endpoint remains:

> strict protected deterministic attempt by the end of Kinnan turn 4.

The ranker reports:

- valid/error games
- T4 assembly
- T4 attempt
- strict protected T4
- Wilson 95% interval
- paired candidate-only vs baseline-only protected outcomes
- exact paired p-value
- slot exposure rate
- protected rate conditional on slot exposure
- paired exposure-only result when available

### Singleton exposure

A one-card mutation can only matter in a fraction of games. v2 therefore
supports `--exposure-card` and records whether tracked cards were observed in
the Kinnan opening/kept hand, protection set, or recognized combo line.

This is intentionally conservative. A later pilot instrumentation change should
add:

- card drawn after keep
- tutor candidate / tutor selected
- Kinnan activation reveal/hit
- cast / activated
- mulligan choice affected
- card present in a deterministic line

The final methodology should always show both:

1. **natural deck-level effect**, and
2. **conditional effect when the changed slot was exposed**.

## Trace policy

The legacy pilot creates detailed traces. v2 immediately deletes successful
traces by default and retains failures plus sparse audits. This reduces artifact
size and disk pressure while preserving debugging evidence.

A deeper pilot refactor should stop building the trace list in memory unless
debug/audit mode is enabled. That is intentionally gated behind the persistent
JVM equivalence test rather than changing two major variables at once.

## Runtime caching

The pinned Forge/Manabrew tarball is cached by:

- OS
- pinned Manabrew commit
- patch hash

A cache hit skips clone/submodule/build completely.

## Next optimizations after the smoke gate

1. Move process ownership into the pilot cleanly instead of the lifecycle proxy.
2. Add an explicit `endSession` / session disposal RPC if Manabrew exposes one.
3. Profile RSS for 1024m / 1280m / 1536m / 2048m heaps.
4. Test 1 vs 2 Forge JVMs per GitHub runner after RSS/CPU profiling.
5. Add primary-endpoint early termination immediately after a qualifying
   protected T4 attempt.
6. Add a compact/no-trace mode inside `run_game()` so successful games never
   allocate the full trace list.
7. Store game rows in Neon and query missing cache keys before dispatch.
8. Let MagicView create experiment specs and dispatch only missing shards.
9. Add sequential deep-confirmation stages instead of fixed 1,600/3,200/5,000
   counts.
10. Separate architecture/package/singleton experiment classes.

## Experiment classes

### Architecture
Multi-card structural changes. Broad parallel search; 1k-10k+ games for finalists.

### Package
2-6 card packages. Moderate samples with paired seeds; 1k-5k for finalists.

### Singleton
100-200 rejection screen only. Serious evaluation requires exposure tracking and
2k-5k+ paired games when the expected effect is small.

Do not interpret a 100/200-game singleton screen as proof of superiority.

## Workflows

- `.github/workflows/kinnan-sim-v2-smoke.yml`
  - verifies JVM-reuse equivalence
  - verifies cache replay does zero Forge starts
  - records timing and max RSS via `/usr/bin/time -v`

- `.github/workflows/kinnan-sim-v2.yml`
  - generic dispatchable candidate array
  - canonical screen/confirmation seed banks
  - 25-game shards
  - up to 20 parallel workers
  - cross-run runtime cache
  - per-shard result cache
  - adaptive rejection before adversarial confirmation
  - 1,600 adversarial games per confirmed deck

## Safety rule

The legacy workflows remain untouched until v2 passes deterministic equivalence
and demonstrates a real wall-clock/RSS improvement. A green workflow is never
accepted as evidence without checking record counts and result content.
