#!/usr/bin/env python3
"""Optimized Forge/Manabrew batch worker.

Key goals:
- reuse one Forge JVM for several games instead of spawning one JVM per game;
- cap heap aggressively but configurably;
- cache completed game results by deterministic simulation key;
- include the full four-deck pod and optimizer code fingerprint in cache identity;
- keep exposure observations generic so cached games can be relabeled for new
  singleton/package hypotheses without rerunning Forge;
- keep full traces only for explicitly requested audit/debug runs;
- emit compact JSON suitable for long-lived result storage;
- run a fixed seat per shard for cleaner pairing and easier caching.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

COMPLETED = {"game_over", "horizon_complete"}


class _NullStderr:
    def read(self, *args: Any, **kwargs: Any) -> str:
        return ""


class _BorrowedProc:
    """Proxy whose lifecycle methods are no-ops for a pooled JVM."""

    def __init__(self, proc: subprocess.Popen[str]):
        self._proc = proc
        self.stdin = proc.stdin
        self.stdout = proc.stdout
        self.stderr = _NullStderr()

    def poll(self) -> int | None:
        return self._proc.poll()

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
        return 0


class ForgeJvmPool:
    def __init__(self, original_popen: Any, *, reuse_games: int, xmx: str, xms: str) -> None:
        self.original_popen = original_popen
        self.reuse_games = max(1, reuse_games)
        self.xmx = xmx
        self.xms = xms
        self.proc: subprocess.Popen[str] | None = None
        self.games_on_proc = 0
        self.starts = 0

    def _close(self) -> None:
        proc = self.proc
        self.proc = None
        self.games_on_proc = 0
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _spawn(self, args: list[str], kwargs: dict[str, Any]) -> subprocess.Popen[str]:
        tuned: list[str] = []
        inserted_memory = False
        for arg in args:
            if isinstance(arg, str) and arg.startswith("-Xmx"):
                if not inserted_memory:
                    tuned.extend([f"-Xms{self.xms}", f"-Xmx{self.xmx}", "-XX:+UseG1GC"])
                    inserted_memory = True
                continue
            tuned.append(arg)
        if not inserted_memory and tuned and tuned[0] == "java":
            tuned[1:1] = [f"-Xms{self.xms}", f"-Xmx{self.xmx}", "-XX:+UseG1GC"]

        spawn_kwargs = dict(kwargs)
        spawn_kwargs["stderr"] = subprocess.DEVNULL
        proc = self.original_popen(tuned, **spawn_kwargs)
        self.starts += 1
        return proc

    def popen(self, args: list[str], **kwargs: Any) -> _BorrowedProc:
        if self.proc is None or self.proc.poll() is not None or self.games_on_proc >= self.reuse_games:
            self._close()
            self.proc = self._spawn(list(args), kwargs)
        self.games_on_proc += 1
        return _BorrowedProc(self.proc)

    def close(self) -> None:
        self._close()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def optimizer_fingerprint() -> str:
    """Fingerprint the execution wrapper so code changes invalidate old cache.

    The validated pilot identifies its own version separately. These files are
    the layers that can alter stopping, pooling, compact instrumentation or cache
    semantics without changing that pilot version.
    """

    names = ["sim_v2_worker.py", "sim_v2_hotpatch.py", "sim_v2_worker_ultra.py"]
    h = hashlib.sha256()
    for name in names:
        path = HERE / name
        if path.exists():
            h.update(name.encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def strict_pt4(result: dict[str, Any]) -> bool:
    t = result.get("firstAttemptTurn")
    certified = bool(
        result.get("certifiedDeterministicAttempt")
        or (result.get("deterministicT4") and t is not None and t <= 4)
    )
    return bool(result.get("protectedAttempt")) and certified


def relabel_exposure(item: dict[str, Any], exposure_cards: list[str]) -> dict[str, Any]:
    """Relabel cached generic observations for the current mutation/package."""

    if "observedCards" in item:
        observed = set(item.get("observedCards") or [])
        exposed = sorted(card for card in exposure_cards if card in observed)
        item = dict(item)
        item["exposureCards"] = exposed
        item["slotExposed"] = bool(exposed)
        generic_events = item.get("observedCardEvents") or []
        item["exposureEvents"] = [e for e in generic_events if e.get("card") in set(exposure_cards)]
    return item


def compact_result(result: dict[str, Any], exposure_cards: list[str]) -> dict[str, Any]:
    seat = str(result.get("kinnanSeat"))
    opening = set((result.get("openingHands") or {}).get(seat, []) or [])
    kept = set((result.get("keptHands") or {}).get(seat, []) or [])
    combo = str(result.get("comboLine") or "")
    protection = set(result.get("protectionAvailable") or [])
    observed = set(result.get("v2ObservedCards") or []) | opening | kept | protection
    exposed = sorted(card for card in exposure_cards if card in observed or card in combo)
    return {
        "pilotVersion": result.get("pilotVersion"),
        "variant": result.get("variant"),
        "variantDeckSha256": result.get("variantDeckSha256"),
        "seed": result.get("seed"),
        "kinnanSeat": result.get("kinnanSeat"),
        "status": result.get("status"),
        "winnerSeat": result.get("winnerSeat"),
        "kinnanWon": bool(result.get("kinnanWon")),
        "firstAssemblyTurn": result.get("firstAssemblyTurn"),
        "firstAttemptTurn": result.get("firstAttemptTurn"),
        "deterministicT4": bool(result.get("deterministicT4")),
        "certifiedDeterministicAttempt": bool(result.get("certifiedDeterministicAttempt")),
        "attemptResolved": bool(result.get("attemptResolved")),
        "protectedAttempt": bool(result.get("protectedAttempt")),
        "strictProtectedT4": strict_pt4(result),
        "comboLine": result.get("comboLine"),
        "primaryFailureCode": result.get("primaryFailureCode"),
        "wallMs": result.get("wallMs"),
        "prompts": result.get("prompts"),
        "mulligans": (result.get("mulligans") or {}).get(seat),
        "openingHand": sorted(opening),
        "keptHand": sorted(kept),
        "observedCards": sorted(observed),
        "exposureCards": exposed,
        "slotExposed": bool(exposed),
        "v2EarlyExit": bool(result.get("v2EarlyExit")),
        "v2DeadlineExit": bool(result.get("v2DeadlineExit")),
    }


def pod_signature(runner: Any, variant: str, seat: int) -> tuple[str, list[str]]:
    """Hash all four deck files in seat order for safe result reuse."""

    ordered = runner.configure_decks(variant, seat)
    hashes = [sha256_file(runner.base.DECK_DIR / filename) for _, filename in ordered]
    payload = [
        {"seat": i, "name": name, "file": filename, "sha256": hashes[i]}
        for i, (name, filename) in enumerate(ordered)
    ]
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return digest, hashes


def cache_key(
    *,
    engine_id: str,
    pilot_version: str,
    optimizer_id: str,
    execution_profile: str,
    deck_sha: str,
    pod_sha: str,
    mode: str,
    pod: str,
    seed: int,
    seat: int,
    max_round: int,
) -> str:
    payload = {
        "engine": engine_id,
        "pilot": pilot_version,
        "optimizer": optimizer_id,
        "profile": execution_profile,
        "deck": deck_sha,
        "podDecks": pod_sha,
        "mode": mode,
        "pod": pod,
        "seed": seed,
        "seat": seat,
        "maxRound": max_round,
        "schema": 4,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def cleanup_game_files(runner: Any, variant: str, seed: int, seat: int, *, keep_trace: bool) -> None:
    suffix = f"{variant}-{seed}-s{seat}"
    result_dir = runner.base.RESULT_DIR
    for p in result_dir.glob(f"pilot-result-{suffix}.json"):
        p.unlink(missing_ok=True)
    for p in result_dir.glob(f"pilot-stderr-{suffix}.log"):
        p.unlink(missing_ok=True)
    if not keep_trace:
        (result_dir / f"pilot-trace-{suffix}.json").unlink(missing_ok=True)
        (result_dir / f"pilot-errors-{suffix}.json").unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("harness_jar")
    ap.add_argument("forge_home")
    ap.add_argument("--mode", choices=("screen", "adversarial"), default="screen")
    ap.add_argument("--variant", required=True)
    ap.add_argument("--seeds", nargs="+", type=int, required=True)
    ap.add_argument("--fixed-seat", type=int, choices=range(4), required=True)
    ap.add_argument("--max-round", type=int, default=4)
    ap.add_argument("--max-prompts", type=int, default=3500)
    ap.add_argument("--max-seconds", type=int, default=90)
    ap.add_argument("--jvm-reuse", type=int, default=8)
    ap.add_argument("--xmx", default="1536m")
    ap.add_argument("--xms", default="256m")
    ap.add_argument("--cache-dir", default=".sim-cache/v2")
    ap.add_argument("--output", required=True)
    ap.add_argument("--engine-id", default=os.getenv("MANABREW_REF", "unknown-engine"))
    ap.add_argument("--exposure-card", action="append", default=[])
    ap.add_argument("--retain-traces", choices=("none", "failures", "all"), default="failures")
    ap.add_argument("--audit-every", type=int, default=50)
    args = ap.parse_args()

    if args.mode == "adversarial":
        import manabrew_pilot_precision_adv as config
    else:
        import manabrew_pilot_precision as config

    runner = config.runner
    if args.variant not in runner.VARIANT_FILES:
        raise SystemExit(f"unknown variant {args.variant}; known={sorted(runner.VARIANT_FILES)}")

    deck_path = runner.base.DECK_DIR / runner.VARIANT_FILES[args.variant]
    deck_sha = sha256_file(deck_path)
    pilot_version = str(runner.PILOT_VERSION)
    optimizer_id = optimizer_fingerprint()
    execution_profile = os.getenv("SIM_V2_PROFILE", "legacy-v2")
    pod = os.getenv("CEDH_POD", "balanced" if args.mode == "adversarial" else "screen")
    pod_sha, seat_deck_hashes = pod_signature(runner, args.variant, args.fixed_seat)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    original_popen = runner.subprocess.Popen
    pool = ForgeJvmPool(original_popen, reuse_games=args.jvm_reuse, xmx=args.xmx, xms=args.xms)
    runner.subprocess.Popen = pool.popen

    results: list[dict[str, Any]] = []
    cache_hits = 0
    started = time.monotonic()
    try:
        for idx, seed in enumerate(args.seeds):
            key = cache_key(
                engine_id=args.engine_id,
                pilot_version=pilot_version,
                optimizer_id=optimizer_id,
                execution_profile=execution_profile,
                deck_sha=deck_sha,
                pod_sha=pod_sha,
                mode=args.mode,
                pod=pod,
                seed=seed,
                seat=args.fixed_seat,
                max_round=args.max_round,
            )
            cache_path = cache_dir / f"{key}.json"
            if cache_path.exists():
                try:
                    item = relabel_exposure(json.loads(cache_path.read_text()), args.exposure_card)
                    results.append(item)
                    cache_hits += 1
                    print(json.dumps({"cacheHit": True, "seed": seed, "key": key}), flush=True)
                    continue
                except Exception:
                    cache_path.unlink(missing_ok=True)

            try:
                raw = runner.run_game(
                    args.harness_jar,
                    args.forge_home,
                    seed,
                    args.variant,
                    args.fixed_seat,
                    max_prompts=args.max_prompts,
                    max_round=args.max_round,
                    max_seconds=args.max_seconds,
                )
            except Exception as exc:
                raw = {
                    "pilotVersion": pilot_version,
                    "variant": args.variant,
                    "variantDeckSha256": deck_sha,
                    "seed": seed,
                    "kinnanSeat": args.fixed_seat,
                    "status": "crash",
                    "error": repr(exc),
                    "primaryFailureCode": "ENGINE_ERROR",
                }

            item = compact_result(raw, args.exposure_card)
            item.update({
                "cacheKey": key,
                "mode": args.mode,
                "pod": pod,
                "podDeckSha256": pod_sha,
                "seatDeckSha256s": seat_deck_hashes,
                "optimizerId": optimizer_id,
                "executionProfile": execution_profile,
            })
            cache_path.write_text(json.dumps(item, separators=(",", ":")))
            results.append(item)

            is_failure = item.get("status") not in COMPLETED
            audit = args.audit_every > 0 and (idx % args.audit_every == 0)
            keep_trace = (
                args.retain_traces == "all"
                or (args.retain_traces == "failures" and (is_failure or audit))
            )
            cleanup_game_files(runner, args.variant, seed, args.fixed_seat, keep_trace=keep_trace)
            print(json.dumps(item, sort_keys=True), flush=True)
    finally:
        runner.subprocess.Popen = original_popen
        pool.close()

    out_path.write_text(json.dumps(results, indent=2))
    completed = sum(item.get("status") in COMPLETED for item in results)
    protected = sum(bool(item.get("strictProtectedT4")) for item in results)
    exposed = sum(bool(item.get("slotExposed")) for item in results)
    summary = {
        "variant": args.variant,
        "mode": args.mode,
        "pod": pod,
        "podDeckSha256": pod_sha,
        "optimizerId": optimizer_id,
        "executionProfile": execution_profile,
        "seat": args.fixed_seat,
        "games": len(results),
        "completed": completed,
        "errors": len(results) - completed,
        "protectedT4": protected,
        "slotExposed": exposed,
        "cacheHits": cache_hits,
        "jvmStarts": pool.starts,
        "jvmReuseTarget": args.jvm_reuse,
        "wallMs": round((time.monotonic() - started) * 1000),
    }
    print("SIM_V2_SUMMARY " + json.dumps(summary, sort_keys=True), flush=True)
    return 0 if len(results) == len(args.seeds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
