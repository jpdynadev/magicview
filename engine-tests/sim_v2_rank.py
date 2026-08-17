#!/usr/bin/env python3
"""Aggregate v2 simulation shards with paired and exposure-aware statistics."""
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
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / d
    return max(0.0, center - margin), min(1.0, center + margin)


def load_games(patterns: list[str]) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    seen = set()
    for pattern in patterns:
        for name in glob.glob(pattern, recursive=True):
            p = Path(name)
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            try:
                payload = json.loads(p.read_text())
            except Exception:
                continue
            if isinstance(payload, list):
                games.extend(x for x in payload if isinstance(x, dict))
    return games


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [g for g in rows if g.get("status") in COMPLETED]
    protected = sum(bool(g.get("strictProtectedT4")) for g in valid)
    attempts = sum(
        bool(
            g.get("certifiedDeterministicAttempt")
            or g.get("attemptResolved")
            or g.get("firstAttemptTurn") is not None
        )
        and (g.get("firstAttemptTurn") is None or g.get("firstAttemptTurn") <= 4)
        for g in valid
    )
    assembly = sum(
        bool(g.get("deterministicT4"))
        or (
            g.get("firstAssemblyTurn") is not None
            and int(g.get("firstAssemblyTurn")) <= 4
        )
        for g in valid
    )
    exposed = [g for g in valid if g.get("slotExposed")]
    exposed_protected = sum(bool(g.get("strictProtectedT4")) for g in exposed)
    n = len(valid)
    lo, hi = wilson(protected, n)
    exp_lo, exp_hi = wilson(exposed_protected, len(exposed))
    wall = [int(g.get("wallMs") or 0) for g in rows if g.get("wallMs") is not None]
    return {
        "games": len(rows),
        "valid": n,
        "errors": len(rows) - n,
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
    }


def key(g: dict[str, Any]) -> tuple[Any, ...]:
    return (
        g.get("mode"),
        g.get("pod"),
        g.get("kinnanSeat"),
        g.get("seed"),
    )


def sequential_decision(
    *,
    candidate_only: int,
    baseline_only: int,
    p: float,
    candidate_rate: float,
    baseline_rate: float,
    paired_n: int,
) -> str:
    discordant = candidate_only + baseline_only
    if paired_n < 80:
        return "MORE_DATA"
    if p <= 0.05 and candidate_only > baseline_only:
        return "PROMOTE"
    if p <= 0.10 and baseline_only > candidate_only:
        return "REJECT"
    if discordant >= 20 and baseline_only >= candidate_only * 1.75:
        return "REJECT"
    if paired_n < 2000 and (
        p <= 0.50
        or abs(candidate_rate - baseline_rate) >= 0.003
        or discordant < 40
    ):
        return "MORE_DATA"
    return "TIE_OR_TINY_EFFECT"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--baseline", default="P00_F10")
    ap.add_argument("--output", default="sim-v2-ranking.json")
    ap.add_argument("--github-output")
    args = ap.parse_args()

    games = load_games(args.patterns)
    if not games:
        raise SystemExit("no v2 game JSON found")

    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in games:
        if g.get("variant"):
            by_variant[str(g["variant"])].append(g)
    if args.baseline not in by_variant:
        raise SystemExit(f"baseline {args.baseline} missing")

    baseline_summary = summarize(by_variant[args.baseline])
    baseline_map = {
        key(g): g
        for g in by_variant[args.baseline]
        if g.get("status") in COMPLETED
    }
    ranking = []
    for variant, rows in by_variant.items():
        s = summarize(rows)
        paired_n = candidate_only = baseline_only = both = neither = 0
        exposed_pairs = exposed_candidate_only = exposed_baseline_only = 0
        if variant != args.baseline:
            cmap = {key(g): g for g in rows if g.get("status") in COMPLETED}
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
            decision = sequential_decision(
                candidate_only=candidate_only,
                baseline_only=baseline_only,
                p=p,
                candidate_rate=s["protectedRate"],
                baseline_rate=baseline_summary["protectedRate"],
                paired_n=paired_n,
            )
        else:
            p = 1.0
            ep = 1.0
            decision = "BASELINE"

        s.update(
            {
                "variant": variant,
                "pairedN": paired_n,
                "candidateOnlyProtected": candidate_only,
                "baselineOnlyProtected": baseline_only,
                "bothProtected": both,
                "neitherProtected": neither,
                "pairedProtectedP": p,
                "exposedPairedN": exposed_pairs,
                "exposedCandidateOnlyProtected": exposed_candidate_only,
                "exposedBaselineOnlyProtected": exposed_baseline_only,
                "exposedPairedP": ep,
                "decision": decision,
            }
        )
        ranking.append(s)

    ranking.sort(
        key=lambda r: (
            r["protectedRate"],
            r["attemptRate"],
            r["assemblyRate"],
            -r["errors"],
        ),
        reverse=True,
    )
    challengers = [r for r in ranking if r["variant"] != args.baseline]
    best = challengers[0]["variant"] if challengers else None
    best_decision = challengers[0]["decision"] if challengers else None
    confirm = [args.baseline, best] if best else [args.baseline]
    out = {
        "baseline": args.baseline,
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
