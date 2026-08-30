#!/usr/bin/env python3
"""Aggregate v2 simulation shards with paired, exposure-aware sequential stats.

Design principles:
- deduplicate immutable cached game keys before counting anything;
- screening is a rejection gate only and can never promote a singleton/package;
- confirmation uses a pre-declared Bonferroni alpha-spending boundary across
  interim looks, avoiding the false-positive inflation of repeated p<=0.05 peeks;
- primary inference is paired exact McNemar on strict protected-T4 outcomes;
- raw rates, exposure-conditional pairs, pod and seat splits remain diagnostics.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

COMPLETED = {"game_over", "horizon_complete"}


def exact_mcnemar(candidate_only: int, baseline_only: int) -> float:
    n = candidate_only + baseline_only
    if n == 0:
        return 1.0
    k = min(candidate_only, baseline_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / d
    return max(0.0, center - margin), min(1.0, center + margin)


def game_identity(g: dict[str, Any]) -> tuple[Any, ...]:
    # cacheKey is globally strongest. Fall back to the canonical pairing tuple
    # for legacy compact files created before cache-key persistence.
    if g.get("cacheKey"):
        return ("cache", g.get("cacheKey"))
    return (
        "legacy",
        g.get("variant"),
        g.get("mode"),
        g.get("pod"),
        g.get("kinnanSeat"),
        g.get("seed"),
    )


def load_games(patterns: list[str]) -> tuple[list[dict[str, Any]], int]:
    dedup: dict[tuple[Any, ...], dict[str, Any]] = {}
    duplicate_count = 0
    seen_paths = set()
    for pattern in patterns:
        for name in glob.glob(pattern, recursive=True):
            p = Path(name)
            if p in seen_paths or not p.is_file():
                continue
            seen_paths.add(p)
            try:
                payload = json.loads(p.read_text())
            except Exception:
                continue
            if not isinstance(payload, list):
                continue
            for row in payload:
                if not isinstance(row, dict):
                    continue
                identity = game_identity(row)
                if identity in dedup:
                    duplicate_count += 1
                    # Prefer a completed record if one copy is partial/error.
                    old = dedup[identity]
                    if old.get("status") not in COMPLETED and row.get("status") in COMPLETED:
                        dedup[identity] = row
                else:
                    dedup[identity] = row
    return list(dedup.values()), duplicate_count


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [g for g in rows if g.get("status") in COMPLETED]
    protected = sum(bool(g.get("strictProtectedT4")) for g in valid)
    attempts = sum(
        bool(g.get("certifiedDeterministicAttempt") or g.get("attemptResolved") or g.get("firstAttemptTurn") is not None)
        and (g.get("firstAttemptTurn") is None or int(g.get("firstAttemptTurn")) <= 4)
        for g in valid
    )
    assembly = sum(
        bool(g.get("deterministicT4"))
        or (g.get("firstAssemblyTurn") is not None and int(g.get("firstAssemblyTurn")) <= 4)
        for g in valid
    )
    exposed = [g for g in valid if g.get("slotExposed")]
    exposed_protected = sum(bool(g.get("strictProtectedT4")) for g in exposed)
    n = len(valid)
    lo, hi = wilson(protected, n)
    exp_lo, exp_hi = wilson(exposed_protected, len(exposed))
    wall = [int(g.get("wallMs") or 0) for g in rows if g.get("wallMs") is not None]
    prompts = [int(g.get("prompts") or 0) for g in rows if g.get("prompts") is not None]
    return {
        "games": len(rows),
        "valid": n,
        "errors": len(rows) - n,
        "errorRate": (len(rows) - n) / max(len(rows), 1),
        "assembly": assembly,
        "assemblyRate": assembly / max(n, 1),
        "attempt": attempts,
        "attemptRate": attempts / max(n, 1),
        "protected": protected,
        "protectedRate": protected / max(n, 1),
        "protectedWilson95": [lo, hi],
        "exposed": len(exposed),
        "exposureRate": len(exposed) / max(n, 1),
        "exposedProtected": exposed_protected,
        "exposedProtectedRate": exposed_protected / max(len(exposed), 1),
        "exposedProtectedWilson95": [exp_lo, exp_hi],
        "wallMsTotal": sum(wall),
        "wallMsMean": sum(wall) / max(len(wall), 1),
        "promptsMean": sum(prompts) / max(len(prompts), 1),
        "positiveEarlyExits": sum(bool(g.get("v2EarlyExit")) for g in rows),
        "deadlineEarlyExits": sum(bool(g.get("v2DeadlineExit")) for g in rows),
    }


def pair_key(g: dict[str, Any]) -> tuple[Any, ...]:
    return (g.get("mode"), g.get("pod"), g.get("kinnanSeat"), g.get("seed"))


def split_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in rows:
        grouped[str(g.get(field))].append(g)
    return {name: summarize(items) for name, items in sorted(grouped.items())}


def sequential_decision(
    *,
    stage: str,
    look: int,
    max_looks: int,
    candidate_only: int,
    baseline_only: int,
    p: float,
    candidate_rate: float,
    baseline_rate: float,
    paired_n: int,
    minimum_effect: float,
) -> tuple[str, dict[str, Any]]:
    discordant = candidate_only + baseline_only
    observed_effect = candidate_rate - baseline_rate
    candidate_discordant_share = candidate_only / max(discordant, 1)
    alpha_each = 0.05 / max(max_looks, 1)
    meta = {
        "stage": stage,
        "look": look,
        "maxLooks": max_looks,
        "alphaSpentThisLook": alpha_each if stage == "confirmation" else 0.0,
        "familywiseAlpha": 0.05,
        "minimumPracticalEffect": minimum_effect,
        "observedAbsoluteEffect": observed_effect,
        "discordant": discordant,
        "candidateDiscordantShare": candidate_discordant_share,
    }

    if paired_n < 80:
        return "MORE_DATA", meta

    if stage == "screen":
        # A small screen may kill an obvious loser but may not establish a new
        # champion. That avoids the methodological error of promoting a singleton
        # on ~100 games where the changed slot may appear only a handful of times.
        if discordant >= 10 and baseline_only >= max(4, candidate_only * 2):
            return "REJECT", meta
        if p <= 0.10 and baseline_only > candidate_only:
            return "REJECT", meta
        return "CONFIRM", meta

    # Confirmation: symmetric alpha-spending. A result at any interim look must
    # beat 0.05/max_looks, so four looks control the total false-positive rate at
    # <=0.05 by Bonferroni even if we stop as soon as a boundary is crossed.
    if p <= alpha_each:
        if candidate_only > baseline_only:
            return "PROMOTE", meta
        if baseline_only > candidate_only:
            return "REJECT", meta

    # Futility / practical equivalence is deliberately conservative. We only
    # stop for tiny effects after substantial paired evidence; otherwise continue
    # until the pre-declared maximum look and call the result inconclusive.
    if paired_n >= 2000 and abs(observed_effect) < minimum_effect and p > 0.50:
        return "TIE_OR_TINY_EFFECT", meta
    if look >= max_looks:
        if abs(observed_effect) < minimum_effect and p > 0.25:
            return "TIE_OR_TINY_EFFECT", meta
        return "INCONCLUSIVE", meta
    return "MORE_DATA", meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--baseline", default="P00_F10")
    ap.add_argument("--output", default="sim-v2-ranking.json")
    ap.add_argument("--github-output")
    ap.add_argument("--stage", choices=("screen", "confirmation"), default="screen")
    ap.add_argument("--look", type=int, default=1)
    ap.add_argument("--max-looks", type=int, default=4)
    ap.add_argument("--minimum-effect", type=float, default=0.003)
    args = ap.parse_args()
    if args.look < 1 or args.look > max(args.max_looks, 1):
        raise SystemExit("look must be between 1 and max-looks")

    games, duplicates = load_games(args.patterns)
    if not games:
        raise SystemExit("no v2 game JSON found")

    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in games:
        if g.get("variant"):
            by_variant[str(g["variant"])].append(g)
    if args.baseline not in by_variant:
        raise SystemExit(f"baseline {args.baseline} missing")

    baseline_summary = summarize(by_variant[args.baseline])
    baseline_map = {pair_key(g): g for g in by_variant[args.baseline] if g.get("status") in COMPLETED}
    ranking = []
    for variant, rows in by_variant.items():
        s = summarize(rows)
        paired_n = candidate_only = baseline_only = both = neither = 0
        exposed_pairs = exposed_candidate_only = exposed_baseline_only = 0
        if variant != args.baseline:
            cmap = {pair_key(g): g for g in rows if g.get("status") in COMPLETED}
            for k, b in baseline_map.items():
                c = cmap.get(k)
                if c is None:
                    continue
                paired_n += 1
                bp = bool(b.get("strictProtectedT4"))
                cp = bool(c.get("strictProtectedT4"))
                if cp and not bp:
                    candidate_only += 1
                elif bp and not cp:
                    baseline_only += 1
                elif bp and cp:
                    both += 1
                else:
                    neither += 1
                if b.get("slotExposed") or c.get("slotExposed"):
                    exposed_pairs += 1
                    if cp and not bp:
                        exposed_candidate_only += 1
                    elif bp and not cp:
                        exposed_baseline_only += 1
            p = exact_mcnemar(candidate_only, baseline_only)
            ep = exact_mcnemar(exposed_candidate_only, exposed_baseline_only)
            decision, stopping = sequential_decision(
                stage=args.stage,
                look=args.look,
                max_looks=args.max_looks,
                candidate_only=candidate_only,
                baseline_only=baseline_only,
                p=p,
                candidate_rate=s["protectedRate"],
                baseline_rate=baseline_summary["protectedRate"],
                paired_n=paired_n,
                minimum_effect=args.minimum_effect,
            )
        else:
            p = ep = 1.0
            decision = "BASELINE"
            stopping = {"stage": args.stage, "look": args.look, "maxLooks": args.max_looks}

        discordant = candidate_only + baseline_only
        paired_effect = (candidate_only - baseline_only) / max(paired_n, 1)
        relative = (
            (s["protectedRate"] / baseline_summary["protectedRate"] - 1)
            if baseline_summary["protectedRate"] > 0
            else None
        )
        s.update({
            "variant": variant,
            "pairedN": paired_n,
            "candidateOnlyProtected": candidate_only,
            "baselineOnlyProtected": baseline_only,
            "bothProtected": both,
            "neitherProtected": neither,
            "discordantPairs": discordant,
            "pairedNetEffect": paired_effect,
            "rawAbsoluteProtectedEffect": s["protectedRate"] - baseline_summary["protectedRate"],
            "rawRelativeProtectedEffect": relative,
            "pairedProtectedP": p,
            "exposedPairedN": exposed_pairs,
            "exposedCandidateOnlyProtected": exposed_candidate_only,
            "exposedBaselineOnlyProtected": exposed_baseline_only,
            "exposedPairedNetEffect": (exposed_candidate_only - exposed_baseline_only) / max(exposed_pairs, 1),
            "exposedPairedP": ep,
            "decision": decision,
            "stoppingRule": stopping,
            "byPod": split_summary(rows, "pod"),
            "bySeat": split_summary(rows, "kinnanSeat"),
        })
        ranking.append(s)

    ranking.sort(key=lambda r: (r["protectedRate"], r["attemptRate"], r["assemblyRate"], -r["errors"]), reverse=True)
    challengers = [r for r in ranking if r["variant"] != args.baseline]
    best = challengers[0]["variant"] if challengers else None
    best_decision = challengers[0]["decision"] if challengers else None
    confirm = [args.baseline, best] if best else [args.baseline]
    out = {
        "baseline": args.baseline,
        "stage": args.stage,
        "look": args.look,
        "maxLooks": args.max_looks,
        "minimumEffect": args.minimum_effect,
        "deduplicatedGames": len(games),
        "duplicateRecordsIgnored": duplicates,
        "ranking": ranking,
        "bestChallenger": best,
        "bestDecision": best_decision,
        "confirm": confirm,
    }
    Path(args.output).write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))

    github_output = args.github_output or os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write("confirm=" + json.dumps(confirm, separators=(",", ":")) + "\n")
            f.write("best=" + (best or "") + "\n")
            f.write("decision=" + (best_decision or "") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
