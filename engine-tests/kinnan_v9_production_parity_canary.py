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


def _selected_live_actions(witness: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every typed action actually submitted to Forge."""
    selected: list[dict[str, Any]] = []
    for event in list(witness.get("promptTrace") or []):
        answer = event.get("submittedAnswer") or {}
        output = answer.get("output") or {}
        if event.get("promptType") != "chooseAction" or output.get("type") != "act":
            continue
        chosen_id = str(output.get("actionId") or "")
        matches = [
            action
            for action in list((event.get("promptInput") or {}).get("actions") or [])
            if str(action.get("id") or action.get("actionId") or "") == chosen_id
        ]
        if len(matches) != 1:
            raise RuntimeError("submitted typed action lacks one exact live action payload")
        selected.append(matches[0])
    if selected:
        return selected

    # Synthetic component goldens created before submitted answers were
    # persisted retain one selected-action witness. Keep that test adapter
    # compatible without using it for live multi-action evidence.
    legacy = witness.get("witness") or {}
    chosen_id = str(legacy.get("chosenActionId") or "")
    chosen_prompt = legacy.get("promptId")
    for event in list(witness.get("promptTrace") or []):
        if event.get("promptId") != chosen_prompt:
            continue
        matches = [
            action
            for action in list((event.get("promptInput") or {}).get("actions") or [])
            if str(action.get("id") or action.get("actionId") or "") == chosen_id
        ]
        if len(matches) == 1:
            return matches
    return []


def _player_mana_total(snapshot: dict[str, Any]) -> int | None:
    """Return player-0's live pool total, or None when Forge did not expose it."""
    for player in list(snapshot.get("players") or []):
        if not isinstance(player, dict) or player.get("id") != "player-0":
            continue
        pool = player.get("manaPool")
        if isinstance(pool, dict):
            amounts = [
                value
                for value in pool.values()
                if isinstance(value, int) and not isinstance(value, bool)
            ]
            return sum(amounts)
        if isinstance(pool, list):
            amounts = [
                item.get("amount")
                for item in pool
                if isinstance(item, dict)
                and isinstance(item.get("amount"), int)
                and not isinstance(item.get("amount"), bool)
            ]
            return sum(amounts)
        return None
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
    observed_reveal_count = 0
    for event in trace:
        # A non-empty revealCards event owned by player-0 is direct Forge
        # evidence that an exact registered main-deck card was revealed. Empty
        # startup warnings, opponent reveals, and player-view library browsers
        # are deliberately excluded.
        if event.get("promptType") == "revealCards":
            prompt_input = event.get("promptInput") or {}
            reveal_cards = list(prompt_input.get("cards") or [])
            if prompt_input.get("ownerPlayerId") == "player-0" and reveal_cards:
                reveal_zone = str(prompt_input.get("zone") or "")
                for revealed_card in reveal_cards:
                    if not isinstance(revealed_card, dict):
                        continue
                    identity = revealed_card.get("identity") or {}
                    registered_name = engine_to_registered.get(
                        str(identity.get("name") or "")
                    )
                    if not registered_name:
                        continue
                    engine_id = str(revealed_card.get("id") or "")
                    if not engine_id:
                        raise RuntimeError(
                            "live player-0 reveal lacks stable engine card identity"
                        )
                    engine_id_to_registered[engine_id] = registered_name
                    row = rows_by_name[registered_name]
                    row["present"] = True
                    row["revealed"] = True
                    row["involved"] = True
                    turn = event.get("turn")
                    if row["firstSeenTurn"] is None and isinstance(turn, int):
                        row["firstSeenTurn"] = turn
                    if reveal_zone and reveal_zone not in row["zones"]:
                        row["zones"].append(reveal_zone)
                    if reveal_zone and engine_id not in previous_zone_by_engine_id:
                        previous_zone_by_engine_id[engine_id] = reveal_zone
                    observed_reveal_count += 1

        # A submitted library-search choice is direct live evidence that the
        # selected registered card was tutored. Record the hidden library
        # origin before the following snapshot exposes its destination.
        if event.get("promptType") == "chooseCards":
            prompt_input = event.get("promptInput") or {}
            presentation = prompt_input.get("presentation") or {}
            answer = event.get("submittedAnswer") or {}
            output = answer.get("output") or {}
            chosen_ids = list(output.get("chosenCardIds") or [])
            library_search = "library" in str(
                presentation.get("description") or ""
            ).casefold()
            if library_search and output.get("type") == "chooseCardsDecision":
                candidates = {
                    str(card.get("id") or ""): card
                    for card in list(prompt_input.get("cards") or [])
                    if isinstance(card, dict) and card.get("id")
                }
                for chosen_id_raw in chosen_ids:
                    chosen_id = str(chosen_id_raw or "")
                    candidate = candidates.get(chosen_id)
                    identity = (candidate or {}).get("identity") or {}
                    registered_name = engine_to_registered.get(
                        str(identity.get("name") or "")
                    )
                    if not chosen_id or not registered_name:
                        raise RuntimeError(
                            "submitted library search choice lacks exact registered identity"
                        )
                    engine_id_to_registered[chosen_id] = registered_name
                    row = rows_by_name[registered_name]
                    row["present"] = True
                    row["tutored"] = True
                    row["involved"] = True
                    turn = event.get("turn")
                    if row["firstSeenTurn"] is None and isinstance(turn, int):
                        row["firstSeenTurn"] = turn
                    if "library" not in row["zones"]:
                        row["zones"].append("library")
                    if previous_zone_by_engine_id.get(chosen_id) != "library":
                        row["zoneChanges"].append({
                            "fromZone": previous_zone_by_engine_id.get(chosen_id),
                            "toZone": "library",
                            "turn": turn,
                            "step": event.get("step"),
                            "promptId": event.get("promptId"),
                        })
                        previous_zone_by_engine_id[chosen_id] = "library"

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

    # Attribute spending only when Forge accepted a payManaCost response and
    # the immediately following live snapshot shows player-0's pool declined.
    # Printed mana costs and action descriptions are never used as evidence.
    observed_mana_payment_count = 0
    observed_mana_spent_total = 0
    for index, event in enumerate(trace):
        if event.get("promptType") != "payManaCost":
            continue
        prompt_input = event.get("promptInput") or {}
        answer = event.get("submittedAnswer") or {}
        output = answer.get("output") or {}
        if (
            prompt_input.get("canConfirmFromPool") is not True
            or output.get("type") != "pay"
        ):
            continue
        before_total = _player_mana_total(event.get("snapshot") or {})
        if before_total is None:
            continue
        following_snapshot = next(
            (
                later.get("snapshot")
                for later in trace[index + 1:]
                if isinstance(later.get("snapshot"), dict)
            ),
            None,
        )
        if following_snapshot is None:
            continue
        after_total = _player_mana_total(following_snapshot)
        if after_total is None or after_total >= before_total:
            continue
        card_id = str(prompt_input.get("cardId") or "")
        registered_name = engine_id_to_registered.get(card_id)
        if not registered_name:
            continue
        spent = before_total - after_total
        row = rows_by_name[registered_name]
        row["manaSpent"] += spent
        row["involved"] = True
        observed_mana_payment_count += 1
        observed_mana_spent_total += spent

    selected_actions = _selected_live_actions(witness)
    attributed_action_count = 0
    for selected in selected_actions:
        card_id = str(selected.get("cardId") or "")
        registered_name = engine_id_to_registered.get(card_id)
        if not registered_name:
            continue
        row = rows_by_name[registered_name]
        action_type = str(selected.get("type") or "")
        row["cast"] = row["cast"] or action_type == "cast"
        row["played"] = row["played"] or action_type in {"cast", "play"}
        row["activated"] = row["activated"] or action_type == "activateAbility"
        row["used"] = row["cast"] or row["played"] or row["activated"]
        row["involved"] = row["involved"] or row["used"]
        for mana in list(selected.get("producedMana") or []):
            color = str(mana.get("color") or "")
            amount = mana.get("amount")
            if color and isinstance(amount, int) and not isinstance(amount, bool):
                row["manaProduced"][color] = int(row["manaProduced"].get(color) or 0) + amount
        if row["used"]:
            attributed_action_count += 1
    selected_action_attributed = (
        bool(selected_actions)
        and attributed_action_count == len(selected_actions)
    )

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
    bounded_horizon_turn = int(witness.get("horizonTurn") or 0)
    bounded_horizon_reached = bool(witness.get("horizonReached"))
    semantic_valid = (
        observed_snapshot_count > 0
        and opening_rows == 7
        and kept_rows == 7
        and observed_rows >= 7
        and selected_action_attributed
        and bool(witness.get("materialActionEffectConfirmed"))
        and (bounded_horizon_turn <= 0 or bounded_horizon_reached)
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
        "observedRevealCount": observed_reveal_count,
        "observedManaPaymentCount": observed_mana_payment_count,
        "observedManaSpentTotal": observed_mana_spent_total,
        "observedCardRows": observed_rows,
        "openingHandRows": opening_rows,
        "keptRows": kept_rows,
        "selectedActionCount": len(selected_actions),
        "attributedActionCount": attributed_action_count,
        "selectedActionAttributed": selected_action_attributed,
        "materialActionCount": int(witness.get("materialActionCount") or 0),
        "repeatedPilotDecisions": bool(witness.get("repeatedPilotDecisions")),
        "materialActionEffectConfirmed": bool(witness.get("materialActionEffectConfirmed")),
        "boundedObservationOnly": bounded_horizon_turn > 0,
        "boundedHorizonTurn": bounded_horizon_turn if bounded_horizon_turn > 0 else None,
        "boundedHorizonReached": bounded_horizon_reached,
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
        horizon_turn=args.horizon_turn,
        max_typed_actions=args.max_typed_actions,
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
    parser.add_argument(
        "--horizon-turn",
        type=int,
        default=0,
        help="component observation horizon in global Forge turns",
    )
    parser.add_argument(
        "--max-typed-actions",
        type=int,
        default=1,
        help="maximum repeated pilot-v9 typed actions before pass-only continuation",
    )
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
