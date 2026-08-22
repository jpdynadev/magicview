#!/usr/bin/env python3
"""Rank architecture screen results with a hard completeness gate.

A variant may advance to confirmation only when:
- F10 has exactly 200 valid completed screen games;
- the variant has exactly 200 valid completed screen games; and
- all 200 variant keys are paired to the 200 F10 baseline keys.

Incomplete variants remain visible in the ranking output but are ineligible.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from collections import defaultdict
from pathlib import Path

COMPLETED = {"game_over", "horizon_complete"}
EXPECTED = 200


def endpoint(game: dict) -> bool:
    return bool(game.get("strictProtectedT4"))


def pexact(b: int, c: int) -> float:
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def load_games(pattern: str) -> dict[str, dict[tuple[int, int], dict]]:
    by: dict[str, dict[tuple[int, int], dict]] = defaultdict(dict)
    for path in glob.glob(pattern, recursive=True):
        if path.endswith("ranking.json"):
            continue
        try:
            data = json.load(open(path))
        except Exception:
            continue
        games = data if isinstance(data, list) else [data]
        for game in games:
            if not isinstance(game, dict) or game.get("status") not in COMPLETED:
                continue
            variant = game.get("variant")
            seed = game.get("seed")
            seat = game.get("kinnanSeat")
            if variant is None or seed is None or seat is None:
                continue
            by[str(variant)][(int(seed), int(seat))] = game
    return by


def rank(by: dict[str, dict[tuple[int, int], dict]]) -> dict:
    base = by.get("F10", {})
    baseline_complete = len(base) == EXPECTED
    baseline_keys = set(base)
    rows = []

    for variant, gmap in by.items():
        valid = len(gmap)
        if variant == "F10":
            paired_keys = sorted(gmap)
        else:
            paired_keys = sorted(baseline_keys & set(gmap))

        protected = sum(endpoint(g) for g in gmap.values())
        exposed = [g for g in gmap.values() if g.get("slotExposed")]
        protected_exposed = sum(endpoint(g) for g in exposed)
        wins = losses = 0
        for key in paired_keys:
            baseline_value = endpoint(base[key])
            candidate_value = endpoint(gmap[key])
            if candidate_value and not baseline_value:
                wins += 1
            if baseline_value and not candidate_value:
                losses += 1

        eligible = (
            variant != "F10"
            and baseline_complete
            and valid == EXPECTED
            and len(paired_keys) == EXPECTED
            and set(gmap) == baseline_keys
        )
        reasons = []
        if variant != "F10":
            if not baseline_complete:
                reasons.append(f"baseline_valid={len(base)}/{EXPECTED}")
            if valid != EXPECTED:
                reasons.append(f"variant_valid={valid}/{EXPECTED}")
            if len(paired_keys) != EXPECTED:
                reasons.append(f"paired={len(paired_keys)}/{EXPECTED}")
            if valid == EXPECTED and baseline_complete and set(gmap) != baseline_keys:
                reasons.append("paired_key_set_mismatch")

        rows.append(
            {
                "variant": variant,
                "valid": valid,
                "protected": protected,
                "protectedRate": protected / max(valid, 1),
                "exposed": len(exposed),
                "exposureRate": len(exposed) / max(valid, 1),
                "protectedWhenExposed": protected_exposed,
                "protectedWhenExposedRate": protected_exposed / max(len(exposed), 1),
                "pairedN": len(paired_keys),
                "pairedWins": wins,
                "pairedLosses": losses,
                "pairedDelta": (wins - losses) / max(len(paired_keys), 1),
                "pairedP": pexact(wins, losses),
                "confirmationEligible": eligible,
                "ineligibleReasons": reasons,
            }
        )

    rows.sort(
        key=lambda row: (
            bool(row["confirmationEligible"]),
            row["protectedRate"],
            row["pairedDelta"],
            row["valid"],
        ),
        reverse=True,
    )
    challengers = [
        row["variant"]
        for row in rows
        if row["confirmationEligible"]
    ][:3]
    confirm = ["F10", *challengers] if baseline_complete and challengers else []

    return {
        "expectedPerVariant": EXPECTED,
        "baselineValid": len(base),
        "baselineComplete": baseline_complete,
        "ranking": rows,
        "confirm": confirm,
        "confirmationBlocked": not bool(confirm),
        "note": (
            "Confirmation requires a complete 200-game F10 baseline and exactly "
            "200 valid, exactly paired screen games for every advancing challenger."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="all/**/*.json")
    parser.add_argument("--output", default="arch-v2-screen-ranking.json")
    args = parser.parse_args()
    out = rank(load_games(args.input))
    Path(args.output).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
