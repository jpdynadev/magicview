#!/usr/bin/env python3
"""Strict ranking gate for the 200-game Kinnan architecture screen.

A challenger may advance only when both baseline and challenger have exactly
200 completed games on the same 200 (seed, kinnanSeat) keys. Partial samples
remain visible in ranking output but are never eligible for confirmation.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
from collections import defaultdict
from pathlib import Path

COMPLETED = {"game_over", "horizon_complete"}
EXPECTED_VALID = 200


def endpoint(game: dict) -> bool:
    return bool(game.get("strictProtectedT4"))


def exact(b: int, c: int) -> float:
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def game_key(game: dict) -> tuple:
    return (game.get("seed"), game.get("kinnanSeat"))


def load_games(root: Path) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = defaultdict(list)
    for raw in glob.glob(str(root / "*.json")):
        path = Path(raw)
        if path.name.endswith("ranking.json") or "runtime" in path.name:
            continue
        try:
            games = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(games, list) and games:
            by[str(games[0].get("variant", "?"))].extend(
                game for game in games if isinstance(game, dict)
            )
    return by


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    by = load_games(args.artifact_dir)
    baseline_valid = [g for g in by.get("F10", []) if g.get("status") in COMPLETED]
    baseline_keys = [game_key(g) for g in baseline_valid]
    baseline_key_set = set(baseline_keys)
    baseline_complete = (
        len(baseline_valid) == EXPECTED_VALID
        and len(baseline_key_set) == EXPECTED_VALID
    )
    baseline = {game_key(g): g for g in baseline_valid} if baseline_complete else {}

    rows: list[dict] = []
    for variant, games in by.items():
        valid = [g for g in games if g.get("status") in COMPLETED]
        keys = [game_key(g) for g in valid]
        key_set = set(keys)
        key_unique = len(key_set) == len(keys)
        paired_complete = baseline_complete and key_set == baseline_key_set
        sample_complete = len(valid) == EXPECTED_VALID and key_unique
        eligible = sample_complete and paired_complete

        ass = sum(bool(g.get("deterministicT4")) for g in valid)
        att = sum(
            g.get("firstAttemptTurn") is not None and g.get("firstAttemptTurn") <= 4
            for g in valid
        )
        prot = sum(endpoint(g) for g in valid)
        wins = sum(bool(g.get("kinnanWon")) for g in valid)
        exposed = [g for g in valid if g.get("slotExposed")]
        exposed_prot = sum(endpoint(g) for g in exposed)
        b = c = cb = cc = 0
        if variant != "F10" and baseline_complete:
            for game in valid:
                base = baseline.get(game_key(game))
                if base is None:
                    continue
                a0, a1 = endpoint(base), endpoint(game)
                b += int(a0 and not a1)
                c += int(a1 and not a0)
                if game.get("slotExposed"):
                    cb += int(a0 and not a1)
                    cc += int(a1 and not a0)

        reasons = []
        if not baseline_complete:
            reasons.append("baseline_not_200_unique_valid_keys")
        if len(valid) != EXPECTED_VALID:
            reasons.append(f"valid_{len(valid)}_of_{EXPECTED_VALID}")
        if not key_unique:
            reasons.append("duplicate_seed_seat_keys")
        if baseline_complete and key_set != baseline_key_set:
            reasons.append("paired_keys_do_not_match_baseline")

        rows.append(
            {
                "variant": variant,
                "valid": len(valid),
                "errors": len(games) - len(valid),
                "uniqueValidKeys": len(key_set),
                "baselineValidKeys": len(baseline_key_set),
                "eligibleForConfirmation": eligible if variant != "F10" else baseline_complete,
                "ineligibleReasons": reasons,
                "assembly": ass,
                "attempt": att,
                "protected": prot,
                "wins": wins,
                "assemblyRate": ass / max(len(valid), 1),
                "attemptRate": att / max(len(valid), 1),
                "protectedRate": prot / max(len(valid), 1),
                "winRate": wins / max(len(valid), 1),
                "exposureCount": len(exposed),
                "protectedGivenExposure": exposed_prot / max(len(exposed), 1),
                "pairedBaselineOnly": b,
                "pairedChallengerOnly": c,
                "pairedP": exact(b, c),
                "conditionalBaselineOnly": cb,
                "conditionalChallengerOnly": cc,
                "conditionalPairedP": exact(cb, cc),
            }
        )

    rows.sort(
        key=lambda r: (
            bool(r["eligibleForConfirmation"]),
            r["protectedRate"],
            r["attemptRate"],
            r["assemblyRate"],
        ),
        reverse=True,
    )
    challengers = [
        r["variant"]
        for r in rows
        if r["variant"] != "F10" and r["eligibleForConfirmation"]
    ][:3]
    confirm = (["F10"] + challengers) if baseline_complete else []
    out = {
        "schema": "architecture-screen-ranking-v2-strict",
        "expectedValidPerVariant": EXPECTED_VALID,
        "baselineComplete": baseline_complete,
        "baselineValid": len(baseline_valid),
        "baselineUniqueKeys": len(baseline_key_set),
        "ranking": rows,
        "confirm": confirm,
    }
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
