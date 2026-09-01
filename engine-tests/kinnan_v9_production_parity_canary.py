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
    _engine_name,
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


def _selected_live_action(witness: dict[str, Any]) -> dict[str, Any] | None:
    chosen_id = str((witness.get("witness") or {}).get("chosenActionId") or "")
    chosen_prompt = (witness.get("witness") or {}).get("promptId")
    for event in list(witness.get("promptTrace") or []):
        if event.get("promptId") != chosen_prompt:
            continue
        for action in list((event.get("promptInput") or {}).get("actions") or []):
            action_id = str(action.get("id") or action.get("actionId") or "")
            if action_id == chosen_id:
                return action
    return None


def _registered_rows(
    deck_path: Path,
    *,
    seed: int,
    replay: int,
    witness: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build exactly 99 rows from live Forge snapshots and submitted actions."""
    commanders, cards = _parse_dck(deck_path, exact_kinnan_registration=True)
    main = cards[len(commanders):]
    deck_hash = _stable_hash({"commanders": commanders, "main": main})
    engine_to_registered = {_engine_name(card): card for card in main}
    if len(engine_to_registered) != 99:
        raise RuntimeError("registered-to-engine card identity is not one-to-one")

    rows_by_name: dict[str, dict[str, Any]] = {}
    for card in main:
        cid = stable_semantic_hash({"deckHash": deck_hash, "registeredCardName": card})
        rows_by_name[card] = {
            "schemaVersion": FULL99_SCHEMA_VERSION,
            "telemetrySource": "live-forge-snapshot-v1",
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
            "present": False,
            "involved": False,
            "essential": False,
            "attemptPresent": False,
            "protectedAttemptPresent": False,
            "naturalWinPresence": False,
            "packageExecution": False,
            "componentCanaryOnly": True,
            "replay": replay,
        }

    trace = list(witness.get("promptTrace") or [])
    opening_engine_ids: set[str] = set()
    kept_opening = False
    for event in trace:
        if event.get("promptType") != "mulligan":
            continue
        answer = event.get("submittedAnswer") or {}
        kept_opening = bool(((answer.get("output") or {}).get("keep")))
        snapshot = event.get("snapshot") or {}
        for zone in list(snapshot.get("zones") or []):
            if zone.get("ownerId") == "player-0" and zone.get("zone") == "hand":
                opening_engine_ids.update(
                    str(card.get("id") or "")
                    for card in list(zone.get("cards") or [])
                    if isinstance(card, dict) and card.get("id")
                )
        break

    engine_id_to_registered: dict[str, str] = {}
    previous_zone_by_engine_id: dict[str, str] = {}
    observed_snapshot_count = 0
    for event in trace:
        snapshot = event.get("snapshot")
        if not isinstance(snapshot, dict):
            continue
        observed_snapshot_count += 1
        turn = snapshot.get("turn")
        step = snapshot.get("step")
        prompt_id = event.get("promptId")
        for zone in list(snapshot.get("zones") or []):
            if zone.get("ownerId") != "player-0":
                continue
            zone_name = str(zone.get("zone") or "")
            for engine_card in list(zone.get("cards") or []):
                if not isinstance(engine_card, dict):
                    continue
                identity = engine_card.get("identity") or {}
                engine_name = str(identity.get("name") or "")
                registered_name = engine_to_registered.get(engine_name)
                engine_id = str(engine_card.get("id") or "")
                if not registered_name or not engine_id:
                    continue
                engine_id_to_registered[engine_id] = registered_name
                row = rows_by_name[registered_name]
                row["present"] = True
                if row["firstSeenTurn"] is None and isinstance(turn, int):
                    row["firstSeenTurn"] = turn
                if zone_name and zone_name not in row["zones"]:
                    row["zones"].append(zone_name)
                previous = previous_zone_by_engine_id.get(engine_id)
                if previous != zone_name:
                    row["zoneChanges"].append({
                        "fromZone": previous,
                        "toZone": zone_name,
                        "turn": turn,
                        "step": step,
                        "promptId": prompt_id,
                    })
                    if (
                        zone_name == "hand"
                        and engine_id not in opening_engine_ids
                        and previous != "hand"
                        and isinstance(turn, int)
                        and turn > 0
                        and row["firstDrawnTurn"] is None
                    ):
                        row["firstDrawnTurn"] = turn
                    previous_zone_by_engine_id[engine_id] = zone_name
                if engine_id in opening_engine_ids:
                    row["openingHand"] = True
                    row["kept"] = kept_opening

    selected = _selected_live_action(witness)
    selected_action_attributed = False
    if selected is not None:
        card_id = str(selected.get("cardId") or "")
        registered_name = engine_id_to_registered.get(card_id)
        if registered_name:
            row = rows_by_name[registered_name]
            action_type = str(selected.get("type") or "")
            row["cast"] = action_type == "cast"
            row["played"] = action_type in {"cast", "play"}
            row["activated"] = action_type == "activateAbility"
            row["used"] = row["cast"] or row["played"] or row["activated"]
            row["involved"] = row["used"]
            for mana in list(selected.get("producedMana") or []):
                color = str(mana.get("color") or "")
                amount = mana.get("amount")
                if color and isinstance(amount, int) and not isinstance(amount, bool):
                    row["manaProduced"][color] = int(row["manaProduced"].get(color) or 0) + amount
            selected_action_attributed = row["used"]

    rows = [rows_by_name[card] for card in main]
    names = [row["registeredCardName"] for row in rows]
    ids = [row["registeredCardId"] for row in rows]
    observed_rows = sum(1 for row in rows if row["present"])
    opening_rows = sum(1 for row in rows if row["openingHand"])
    kept_rows = sum(1 for row in rows if row["kept"])
    structural_valid = (
        len(rows) == 99
        and len(set(names)) == 99
        and len(set(ids)) == 99
    )
    semantic_valid = (
        observed_snapshot_count > 0
        and opening_rows == 7
        and kept_rows == 7
        and observed_rows >= 7
        and selected_action_attributed
        and bool(witness.get("materialActionEffectConfirmed"))
    )
    coverage = {
        "schemaVersion": FULL99_SCHEMA_VERSION,
        "telemetrySource": "live-forge-snapshot-v1",
        "validGames": 1,
        "expectedRows": 99,
        "actualRows": len(rows),
        "distinctRegisteredCards": len(set(names)),
        "distinctRegisteredCardIds": len(set(ids)),
        "missingCards": [],
        "duplicates": len(rows) - len(set(ids)),
        "observedSnapshotCount": observed_snapshot_count,
        "observedCardRows": observed_rows,
        "openingHandRows": opening_rows,
        "keptRows": kept_rows,
        "selectedActionAttributed": selected_action_attributed,
        "materialActionEffectConfirmed": bool(witness.get("materialActionEffectConfirmed")),
        "structuralValid": structural_valid,
        "semanticValid": semantic_valid,
        "valid": structural_valid and semantic_valid,
        "componentCanaryOnly": True,
        "rawActionTraceHash": stable_semantic_hash(trace),
    }
    return rows, coverage


def _canonical_telemetry_hash(rows: list[dict[str, Any]]) -> str:
    """Compare replay observations while excluding replay-local prompt identity."""
    canonical: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        row.pop("replay", None)
        row["zoneChanges"] = [
            {key: value for key, value in change.items() if key != "promptId"}
            for change in list(row.get("zoneChanges") or [])
        ]
        canonical.append(row)
    return stable_semantic_hash(canonical)


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
        first_telemetry_hash = _canonical_telemetry_hash(
            list(first.get("full99V3Rows") or [])
        )
        second_telemetry_hash = _canonical_telemetry_hash(
            list(second.get("full99V3Rows") or [])
        )
        telemetry_replay_equal = first_telemetry_hash == second_telemetry_hash
        replay_equal = (
            first.get("deterministicWitnessHash") == second.get("deterministicWitnessHash")
            and first.get("registrationAudit", {}).get("registeredDeckSha256")
            == second.get("registrationAudit", {}).get("registeredDeckSha256")
            and first.get("semanticActionTraceHash") == second.get("semanticActionTraceHash")
            and telemetry_replay_equal
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
                "telemetryReplayEqual": telemetry_replay_equal,
                "canonicalTelemetryHashes": [
                    first_telemetry_hash,
                    second_telemetry_hash,
                ],
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
