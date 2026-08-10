#!/usr/bin/env python3
"""Aggregate the fixed-N B0/B2 paired screening stage.

Screening is descriptive by preregistration: this script reports rates,
Wilson intervals, paired changes, and failure mechanisms, but makes no
significance claim and does not reuse these seeds for confirmation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any, Callable


COMPLETE = {"game_over", "horizon_complete"}
VARIANTS = ("B0", "B2")


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if not n:
        return [0.0, 0.0]
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [center - half, center + half]


def primary(row: dict[str, Any]) -> bool:
    turn = row.get("firstAttemptTurn")
    return bool(row.get("protectedAttempt") and turn is not None and turn <= 4)


METRICS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "deterministic_t3": lambda row: bool(row.get("deterministicT3")),
    "deterministic_t4": lambda row: bool(row.get("deterministicT4")),
    "attempt_t4": lambda row: row.get("firstAttemptTurn") is not None and row["firstAttemptTurn"] <= 4,
    "protected_attempt_t4": primary,
    "attempt_resolved": lambda row: bool(row.get("attemptResolved")),
    "kinnan_won": lambda row: bool(row.get("kinnanWon")),
}


def paired_bootstrap(values: list[float], draws: int = 10000) -> list[float]:
    if not values:
        return [0.0, 0.0]
    rng = random.Random(20260810)
    n = len(values)
    samples = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(draws))
    return [samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]]


def load_rows(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("pilot-result-*.json")):
        row = json.loads(path.read_text())
        row["sourceFile"] = str(path.relative_to(root))
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-pairs", type=int, default=200)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    rows = load_rows(args.input)
    keyed: dict[tuple[int, int, str], dict[str, Any]] = {}
    duplicates = []
    for row in rows:
        key = (int(row["seed"]), int(row["kinnanSeat"]), str(row["variant"]))
        if key in keyed:
            duplicates.append(key)
        keyed[key] = row

    pairs = []
    incomplete = []
    scenario_keys = sorted({(seed, seat) for seed, seat, _ in keyed})
    for seed, seat in scenario_keys:
        pair = {variant: keyed.get((seed, seat, variant)) for variant in VARIANTS}
        if any(pair[variant] is None or pair[variant].get("status") not in COMPLETE for variant in VARIANTS):
            incomplete.append({"seed": seed, "seat": seat, "rows": pair})
        else:
            pairs.append({"seed": seed, "seat": seat, **pair})

    summary: dict[str, Any] = {
        "stage": "screening",
        "inferentialClaim": False,
        "pilotVersion": "v8.3.0",
        "engineAdapterPatch": "manabrew-card-name-runaway-2",
        "expectedPairs": args.expected_pairs,
        "observedRows": len(rows),
        "completePairs": len(pairs),
        "duplicateKeys": duplicates,
        "incompleteScenarios": incomplete,
        "variants": {},
        "paired": {},
    }

    for variant in VARIANTS:
        vrows = [pair[variant] for pair in pairs]
        metric_summary = {}
        for name, predicate in METRICS.items():
            successes = sum(predicate(row) for row in vrows)
            metric_summary[name] = {
                "successes": successes,
                "n": len(vrows),
                "rate": successes / len(vrows) if vrows else 0.0,
                "wilson95": wilson(successes, len(vrows)),
            }
        summary["variants"][variant] = {
            "deckSha256": sorted({row.get("variantDeckSha256") for row in vrows}),
            "metrics": metric_summary,
            "failureCounts": dict(sorted(Counter(row.get("primaryFailureCode") or "NONE" for row in vrows).items())),
            "seatPrimary": {
                str(seat): {
                    "successes": sum(primary(row) for row in vrows if row["kinnanSeat"] == seat),
                    "n": sum(row["kinnanSeat"] == seat for row in vrows),
                }
                for seat in range(4)
            },
            "medianMulligans": sorted(row.get("mulligans", {}).get(str(row["kinnanSeat"]), 0) for row in vrows)[len(vrows) // 2]
            if vrows
            else None,
        }

    for name, predicate in METRICS.items():
        changes = [float(predicate(pair["B2"])) - float(predicate(pair["B0"])) for pair in pairs]
        improve = sum(value > 0 for value in changes)
        regress = sum(value < 0 for value in changes)
        summary["paired"][name] = {
            "delta": sum(changes) / len(changes) if changes else 0.0,
            "pairedBootstrap95": paired_bootstrap(changes),
            "failToSuccess": improve,
            "successToFail": regress,
            "unchanged": len(changes) - improve - regress,
        }

    valid = (
        len(pairs) == args.expected_pairs
        and not duplicates
        and not incomplete
        and len(rows) == args.expected_pairs * len(VARIANTS)
    )
    summary["screenComplete"] = valid
    (args.output / "screen-summary.json").write_text(json.dumps(summary, indent=2))

    with (args.output / "paired-games.csv").open("w", newline="") as handle:
        columns = ["seed", "seat", "variant", "status", *METRICS, "failure", "mulligans", "wall_ms"]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for pair in pairs:
            for variant in VARIANTS:
                row = pair[variant]
                writer.writerow(
                    {
                        "seed": pair["seed"],
                        "seat": pair["seat"],
                        "variant": variant,
                        "status": row["status"],
                        **{metric: int(predicate(row)) for metric, predicate in METRICS.items()},
                        "failure": row.get("primaryFailureCode"),
                        "mulligans": row.get("mulligans", {}).get(str(pair["seat"])),
                        "wall_ms": row.get("wallMs"),
                    }
                )

    lines = [
        "# Kinnan B0 vs B2 — 200-pair screening report",
        "",
        "> Descriptive screening only. These seeds are excluded from confirmation.",
        "",
        f"- Complete pairs: **{len(pairs)}/{args.expected_pairs}**",
        f"- Screen complete: **{valid}**",
        "",
        "| Variant | T3 assembly | T4 assembly | Protected T4 attempt | Resolved | Kinnan win |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        metrics = summary["variants"][variant]["metrics"]
        lines.append(
            f"| {variant} | {metrics['deterministic_t3']['rate']:.1%} | "
            f"{metrics['deterministic_t4']['rate']:.1%} | {metrics['protected_attempt_t4']['rate']:.1%} | "
            f"{metrics['attempt_resolved']['rate']:.1%} | {metrics['kinnan_won']['rate']:.1%} |"
        )
    delta = summary["paired"]["protected_attempt_t4"]
    lines += [
        "",
        f"B2 paired protected-attempt delta: **{delta['delta']:+.1%}** "
        f"(screening bootstrap 95% interval {delta['pairedBootstrap95'][0]:+.1%} to "
        f"{delta['pairedBootstrap95'][1]:+.1%}); transitions "
        f"{delta['failToSuccess']} fail→success, {delta['successToFail']} success→fail.",
    ]
    (args.output / "screen-report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"screenComplete": valid, "pairs": len(pairs)}, sort_keys=True))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
