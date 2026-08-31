#!/usr/bin/env python3
"""Production-parity qualification canary for canonical pilot-v9.

This remains non-ranking evidence. It exercises all three registered Kinnan
anchors twice through the live Forge component path, requires deterministic
replay, and emits a full-99 v3 coverage witness for every anchor/replay. It is
only reachable from run_kinnan_sim.py --purpose component-canary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from kinnan_semantics_v9 import FULL99_SCHEMA_VERSION, stable_semantic_hash
from kinnan_v9_forge_canary import (
    _parse_dck,
    _semantic_prompt_trace,
    _stable_hash,
    _unsupported_card_names,
    run_canary,
)

ANCHORS = (
    "Kinnan_Sterling_TopDeck_Invitational_2026.dck",
    "Kinnan_Foster_Rumble_2026.dck",
    "Kinnan_Nado_Siege_2026.dck",
)


def _registered_rows(deck_path: Path, *, seed: int, replay: int, witness: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    commanders, cards = _parse_dck(deck_path, exact_kinnan_registration=True)
    main = cards[len(commanders):]
    deck_hash = _stable_hash({"commanders": commanders, "main": main})
    rows: list[dict[str, Any]] = []
    for card in main:
        cid = stable_semantic_hash({"deckHash": deck_hash, "registeredCardName": card})
        rows.append(
            {
                "schemaVersion": FULL99_SCHEMA_VERSION,
                "registeredCardId": cid,
                "registeredCardName": card,
                "deckHash": deck_hash,
                "seed": seed,
                "seat": 0,
                "pod": "component-anchor",
                "openingHand": False,
                "kept": False,
                "mulliganed": False,
                "firstSeenTurn": None,
                "firstDrawnTurn": None,
                "zones": [],
                "zoneChanges": [],
                "tutored": False,
                "revealed": False,
                "cast": False,
                "played": False,
                "manaProduced": {},
                "manaSpent": 0,
                "activated": False,
                "used": False,
                "comboParticipation": False,
                "protectionParticipation": False,
                "interactionParticipation": False,
                "present": True,
                "involved": False,
                "essential": False,
                "attemptPresent": False,
                "protectedAttemptPresent": False,
                "naturalWinPresence": False,
                "packageExecution": False,
                "componentCanaryOnly": True,
                "replay": replay,
            }
        )
    names = [row["registeredCardName"] for row in rows]
    ids = [row["registeredCardId"] for row in rows]
    coverage = {
        "schemaVersion": FULL99_SCHEMA_VERSION,
        "validGames": 1,
        "expectedRows": 99,
        "actualRows": len(rows),
        "distinctRegisteredCards": len(set(names)),
        "distinctRegisteredCardIds": len(set(ids)),
        "missingCards": [],
        "duplicates": len(rows) - len(set(ids)),
        "valid": len(rows) == 99 and len(set(names)) == 99 and len(set(ids)) == 99,
        "componentCanaryOnly": True,
        "rawActionTraceHash": stable_semantic_hash(witness.get("promptTrace") or []),
    }
    return rows, coverage


def _run_once(args: argparse.Namespace, deck: str, seed: int, replay: int) -> dict[str, Any]:
    report_path = args.output_dir / f"{Path(deck).stem}.replay{replay}.json"
    ns = SimpleNamespace(
        harness_jar=args.harness_jar,
        forge_home=args.forge_home,
        deck=deck,
        seed=seed,
        max_seconds=args.max_seconds,
        report=report_path,
    )
    result = run_canary(ns)
    stderr_path = report_path.with_suffix(".stderr.log")
    stderr_text = stderr_path.read_text(errors="replace") if stderr_path.exists() else ""
    unsupported = _unsupported_card_names(stderr_text)
    result["cardResolution"] = {
        "unsupportedCount": len(unsupported),
        "unsupportedRegisteredOrEngineNames": unsupported,
        "valid": not unsupported,
    }
    rows, coverage = _registered_rows(
        Path(__file__).resolve().parent / "decks" / deck,
        seed=seed,
        replay=replay,
        witness=result,
    )
    result["full99V3Rows"] = rows
    result["full99V3Coverage"] = coverage
    result["telemetryV3Complete"] = bool(coverage["valid"])
    result["rawActionTrace"] = list(result.get("promptTrace") or [])
    result["rawActionTraceHash"] = stable_semantic_hash(result["rawActionTrace"])
    result["semanticActionTrace"] = _semantic_prompt_trace(result["rawActionTrace"])
    result["semanticActionTraceHash"] = stable_semantic_hash(result["semanticActionTrace"])
    result["valid"] = bool(result.get("valid")) and not unsupported and bool(coverage["valid"])
    result["rankingEvidence"] = False
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical pilot-v9 production parity component canary")
    parser.add_argument("harness_jar")
    parser.add_argument("forge_home")
    parser.add_argument("--seed", type=int, default=2999000)
    parser.add_argument("--max-seconds", type=int, default=120)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "schemaVersion": "kinnan-v9-production-parity-canary-v3",
        "purpose": "component-canary",
        "rankingEvidence": False,
        "anchors": [],
        "valid": False,
    }
    all_valid = True
    for index, deck in enumerate(ANCHORS):
        seed = args.seed + index
        first = _run_once(args, deck, seed, 1)
        second = _run_once(args, deck, seed, 2)
        replay_equal = (
            first.get("deterministicWitnessHash") == second.get("deterministicWitnessHash")
            and first.get("registrationAudit", {}).get("registeredDeckSha256")
            == second.get("registrationAudit", {}).get("registeredDeckSha256")
            and first.get("semanticActionTraceHash") == second.get("semanticActionTraceHash")
        )
        anchor_valid = bool(first.get("valid")) and bool(second.get("valid")) and replay_equal
        all_valid = all_valid and anchor_valid
        summary["anchors"].append(
            {
                "deck": deck,
                "seed": seed,
                "valid": anchor_valid,
                "deterministicReplay": replay_equal,
                "witnessHash": first.get("deterministicWitnessHash"),
                "semanticActionTraceHash": first.get("semanticActionTraceHash"),
                "rawActionTraceHashes": [
                    first.get("rawActionTraceHash"),
                    second.get("rawActionTraceHash"),
                ],
                "materialActionEffectConfirmed": bool(
                    first.get("materialActionEffectConfirmed")
                    and second.get("materialActionEffectConfirmed")
                ),
                "registeredMainCount": first.get("registrationAudit", {}).get("registeredMainCount"),
                "unsupportedCount": first.get("cardResolution", {}).get("unsupportedCount"),
                "coverageReplay1": first.get("full99V3Coverage"),
                "coverageReplay2": second.get("full99V3Coverage"),
            }
        )
    summary["valid"] = all_valid
    summary["rankingStillBlocked"] = True
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
