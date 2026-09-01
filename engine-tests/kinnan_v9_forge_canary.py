#!/usr/bin/env python3
"""Live Forge protocol canary for the canonical pilot-v9 path.

This is intentionally not a game simulation and never creates ranking evidence.
It starts the pinned interactive harness, advances pregame prompts for the
external Kinnan seat, submits one real typed ``chooseAction`` selected by
pilot-v9, and proves Forge accepted it by reaching a later phase. Any missing
stable identity or state transition fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import manabrew_pilot_v9 as pilot

HERE = Path(__file__).resolve().parent
DECK_DIR = HERE / "decks"

# Forge indexes modal double-faced cards by their front face. The exact deck
# registration remains the full printed name; only the engine lookup key is
# normalized. Keeping both values is required for full-99 v3 attribution.
MDFC_SEPARATOR = " // "
UNSUPPORTED_CARD_RE = re.compile(
    r'An unsupported card was requested: "([^"]+)"'
)


def _engine_name(registered_name: str) -> str:
    return registered_name.split(MDFC_SEPARATOR, 1)[0].strip()


def _registration_audit(commanders: list[str], cards: list[str]) -> dict[str, Any]:
    registered_main = cards[len(commanders):]
    mappings = [
        {
            "registeredIndex": index,
            "registeredCardName": name,
            "engineCardName": _engine_name(name),
            "mapped": _engine_name(name) != name,
        }
        for index, name in enumerate(registered_main, start=1)
    ]
    canonical = {
        "commanders": commanders,
        "main": registered_main,
    }
    return {
        "registeredCommanderCount": len(commanders),
        "registeredMainCount": len(registered_main),
        "registeredDistinctMainCount": len(set(registered_main)),
        "registeredDeckSha256": _stable_hash(canonical),
        "mappedCardCount": sum(1 for item in mappings if item["mapped"]),
        "registeredToEngine": mappings,
    }


def _unsupported_card_names(stderr_text: str) -> list[str]:
    return sorted(set(UNSUPPORTED_CARD_RE.findall(stderr_text)))


def _parse_dck(path: Path, *, exact_kinnan_registration: bool) -> tuple[list[str], list[str]]:
    section = ""
    commanders: list[str] = []
    main: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.lower()
            continue
        if not line[0].isdigit() or " " not in line:
            continue
        count_text, name = line.split(" ", 1)
        cards = commanders if section == "[commander]" else main if section == "[main]" else None
        if cards is not None:
            cards.extend([name.split("|", 1)[0].strip()] * int(count_text))
    if exact_kinnan_registration:
        if len(commanders) != 1 or len(main) != 99 or len(set(main)) != 99:
            raise RuntimeError(f"invalid exact Kinnan registration: {path}")
    elif len(commanders) not in {1, 2} or len(commanders) + len(main) != 100:
        raise RuntimeError(f"invalid opponent Commander registration: {path}")
    return commanders, commanders + main


def _player(
    name: str,
    deck_file: str,
    *,
    ai: bool,
    exact_kinnan_registration: bool = False,
) -> dict[str, Any]:
    commanders, cards = _parse_dck(
        DECK_DIR / deck_file,
        exact_kinnan_registration=exact_kinnan_registration,
    )
    engine_commanders = [_engine_name(card) for card in commanders]
    return {
        "name": name,
        "commanderNames": engine_commanders,
        "deck": [
            {
                "name": _engine_name(card),
                # Unknown JSON fields are ignored by the pinned adapter, but
                # this keeps exact registration identity alongside lookup
                # identity in the durable start-game payload.
                "registeredName": card,
            }
            for card in cards
        ],
        "ai": ai,
    }


def _rpc(proc: subprocess.Popen[str], request: dict[str, Any]) -> str:
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("Forge interactive harness closed stdout")
    response = json.loads(line)
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "Forge RPC failed"))
    return str(response.get("result") or "")


def _submit(proc: subprocess.Popen[str], session_id: str, answer: dict[str, Any]) -> None:
    _rpc(
        proc,
        {
            "command": "submitAction",
            "sessionId": session_id,
            "payload": json.dumps(answer, separators=(",", ":")),
        },
    )


def _pregame_answer(prompt_input: dict[str, Any]) -> dict[str, Any] | None:
    prompt_type = str(prompt_input.get("type") or "")
    if prompt_type in {"revealCards", "diceRolled"}:
        return {"type": prompt_type, "output": {}}
    if prompt_type == "mulligan":
        return {"type": "mulligan", "output": {"type": "mulliganDecision", "keep": True}}
    if prompt_type == "chooseAttackers":
        # Passing through combat in a component canary is represented by an
        # empty assignment list. No creature identity or target is invented.
        return {
            "type": "chooseAttackers",
            "output": {
                "type": "declareAttackers",
                "assignments": [],
            },
        }
    if prompt_type == "chooseBlockers":
        attackers = list(prompt_input.get("attackers") or [])
        if attackers and all(
            isinstance(attacker, dict)
            and attacker.get("mustBeBlocked") is False
            for attacker in attackers
        ):
            # Protocol v1 omits creatures left back. Empty assignments are a
            # legal deterministic pass only when no attacker must be blocked.
            return {
                "type": "chooseBlockers",
                "output": {
                    "type": "declareBlockers",
                    "assignments": [],
                },
            }
        return None
    if prompt_type == "chooseFromSelection":
        minimum = prompt_input.get("minTotal")
        maximum = prompt_input.get("maxTotal")
        if (
            isinstance(minimum, int)
            and not isinstance(minimum, bool)
            and isinstance(maximum, int)
            and not isinstance(maximum, bool)
            and minimum == 0
            and maximum >= 0
        ):
            # Protocol v1 represents declining an optional selection with an
            # empty chosen-index list. This matches v9's deterministic policy
            # for optional pregame effects and avoids inventing follow-up
            # costs such as an arbitrary Gemstone Caverns exile.
            return {
                "type": "chooseFromSelection",
                "output": {
                    "type": "selectionDecision",
                    "chosenIndices": [],
                },
            }
        options = list(prompt_input.get("options") or [])
        if (
            isinstance(minimum, int)
            and not isinstance(minimum, bool)
            and isinstance(maximum, int)
            and not isinstance(maximum, bool)
            and minimum == maximum == 1
            and len(options) > 1
            and all(isinstance(option, dict) for option in options)
            and all(option == options[0] for option in options[1:])
        ):
            # Forge can emit duplicate mandatory replacement-effect modes
            # without source IDs (for example two byte-identical Venom Blast
            # entries). No observable policy distinction exists, so choose
            # the first canonical index. Distinct or singleton required modes
            # remain fail-closed.
            return {
                "type": "chooseFromSelection",
                "output": {
                    "type": "selectionDecision",
                    "chosenIndices": [0],
                },
            }
        return None
    if prompt_type == "chooseCards":
        # Match Manabrew protocol v1's forced-choice resolver exactly. An
        # empty choice is deterministic when max <= 0, and selecting every
        # offered card is deterministic when min >= the candidate count.
        # Any genuine choice remains visible to pilot policy and fails closed
        # here rather than silently changing game semantics.
        cards = list(prompt_input.get("cards") or [])
        card_ids = [
            str(card.get("id") or "") if isinstance(card, dict) else ""
            for card in cards
        ]
        minimum = prompt_input.get("min")
        maximum = prompt_input.get("max")
        if isinstance(maximum, int) and not isinstance(maximum, bool) and maximum <= 0:
            chosen_ids: list[str] = []
        elif (
            isinstance(minimum, int)
            and not isinstance(minimum, bool)
            and minimum >= len(card_ids)
            and all(card_ids)
            and len(set(card_ids)) == len(card_ids)
        ):
            chosen_ids = card_ids
        elif (
            isinstance(minimum, int)
            and not isinstance(minimum, bool)
            and isinstance(maximum, int)
            and not isinstance(maximum, bool)
            and minimum == maximum
            and minimum > 0
            and str((prompt_input.get("presentation") or {}).get("title") or "").lower()
            == "discard"
        ):
            chosen = pilot.choose_discard(cards, count=minimum)
            chosen_ids = [
                str(card.get("id") or card.get("cardId") or "")
                for card in chosen
            ]
        else:
            return None
        return {
            "type": "chooseCards",
            "output": {
                "type": "chooseCardsDecision",
                "chosenCardIds": chosen_ids,
            },
        }
    return None


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _material_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return engine state that cannot change from priority/phase movement alone."""
    player_fields = (
        "id", "life", "manaPool", "counters", "status", "commanderDamage",
        "hasCityBlessing", "ringLevel", "speed",
    )
    return {
        "players": [
            {key: player.get(key) for key in player_fields}
            for player in list(snapshot.get("players") or [])
            if isinstance(player, dict)
        ],
        "zones": list(snapshot.get("zones") or []),
        "stack": list(snapshot.get("stack") or []),
        "combatAssignments": snapshot.get("combatAssignments"),
        "gameOver": snapshot.get("gameOver"),
        "dayTime": snapshot.get("dayTime"),
    }


def _kinnan_horizon_reached(
    snapshot: dict[str, Any],
    observed_turns: set[int],
    target_kinnan_turn: int,
) -> bool:
    """Track player-0 turns and close only after that player's target turn."""
    turn = snapshot.get("turn")
    active_player_id = snapshot.get("activePlayerId")
    if (
        active_player_id == "player-0"
        and isinstance(turn, int)
        and not isinstance(turn, bool)
        and turn > 0
    ):
        observed_turns.add(turn)
    if target_kinnan_turn <= 0 or len(observed_turns) < target_kinnan_turn:
        return False
    last_kinnan_turn = max(observed_turns)
    step = str(snapshot.get("step") or "")
    return bool(
        (
            active_player_id == "player-0"
            and turn == last_kinnan_turn
            and step == "endOfTurn"
        )
        or (
            isinstance(turn, int)
            and not isinstance(turn, bool)
            and turn > last_kinnan_turn
        )
    )


def _chosen_cost_confirmation(
    prompt_input: dict[str, Any],
    witness: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Accept only the cost confirmation caused by the selected typed action."""
    if not witness or str(prompt_input.get("type") or "") != "chooseBoolean":
        return None
    title = str((prompt_input.get("presentation") or {}).get("title") or "").strip()
    description = str(witness.get("chosenActionDescription") or "").strip()
    cost = str(witness.get("chosenActionCost") or "").strip()
    title_folded = title.casefold()
    cost_clauses = [
        clause.strip().casefold()
        for clause in cost.split(",")
        if clause.strip()
    ]
    description_folded = description.casefold()
    template_clause_match = any(
        re.fullmatch(
            re.escape(clause).replace(re.escape("cardname"), r".+?"),
            title_folded,
        )
        for clause in cost_clauses
        if "cardname" in clause
    )
    # Forge stages compound activation costs as separate Accept/Decline
    # prompts and substitutes the live card name for CARDNAME. Accept a stage
    # only when its complete title is present in the selected action text and
    # exactly matches either a literal cost clause or that clause's CARDNAME
    # template. Unrelated booleans continue to fail closed.
    matches_selected_action = bool(description) and (
        description_folded.startswith(title_folded)
        or (
            title_folded in description_folded
            and (
                title_folded in cost_clauses
                or template_clause_match
            )
        )
    )
    if (
        not title
        or not matches_selected_action
        or str(prompt_input.get("confirmLabel") or "").casefold() != "accept"
        or str(prompt_input.get("denyLabel") or "").casefold() != "decline"
    ):
        return None
    return {
        "type": "chooseBoolean",
        "output": {"type": "decision", "value": True},
    }


def _chosen_optional_entry_payment(
    prompt_input: dict[str, Any],
    witness: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Decline only the selected land's explicit optional ETB life payment."""
    if not witness or str(prompt_input.get("type") or "") != "chooseBoolean":
        return None
    presentation = prompt_input.get("presentation") or {}
    title = str(presentation.get("title") or "").strip()
    text = str(presentation.get("text") or "").strip()
    action_label = str(witness.get("chosenActionLabel") or "").strip()
    action_type = str(witness.get("chosenActionType") or "").strip()
    if (
        action_type not in {"cast", "play"}
        or not action_label.casefold().startswith("play ")
        or not re.fullmatch(r"Pay [1-9][0-9]* \{LIFE\}\?", title)
        or text.casefold() != 'otherwise: "enters tapped."'
        or str(prompt_input.get("confirmLabel") or "").casefold() != "pay"
        or str(prompt_input.get("denyLabel") or "").casefold() != "decline"
    ):
        return None
    # The prompt itself is authoritative evidence of an optional ETB payment.
    # Component qualification declines it deterministically; no printed card
    # text, life total, or strategic ranking policy is inferred.
    return {
        "type": "chooseBoolean",
        "output": {"type": "decision", "value": False},
    }


def _chosen_action_card_selection(
    prompt_input: dict[str, Any],
    witness: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve a library selection caused by the currently selected action."""
    if not witness or str(prompt_input.get("type") or "") != "chooseCards":
        return None
    title = str((prompt_input.get("presentation") or {}).get("title") or "").strip()
    description = str(witness.get("chosenActionDescription") or "").strip()
    cards = list(prompt_input.get("cards") or [])
    minimum = prompt_input.get("min")
    maximum = prompt_input.get("max")
    if (
        not title
        or title.casefold() not in description.casefold()
        or "search your library" not in description.casefold()
        or not cards
        or not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or minimum < 0
        or maximum < 1
    ):
        return None
    pilot_prompt = {
        "input": {
            **prompt_input,
            "selectionKind": "search",
            "mayFailToFind": minimum == 0,
        }
    }
    chosen = pilot.choose_cards(
        pilot_prompt,
        cards,
        desired_roles=("mana_source",),
    )
    chosen_ids = [
        str(card.get("id") or card.get("cardId") or "")
        for card in chosen
    ]
    if (
        not chosen_ids
        or len(chosen_ids) > maximum
        or any(not card_id for card_id in chosen_ids)
        or len(set(chosen_ids)) != len(chosen_ids)
    ):
        return None
    return {
        "type": "chooseCards",
        "output": {
            "type": "chooseCardsDecision",
            "chosenCardIds": chosen_ids,
        },
    }


def _pay_mana_cost_answer(
    prompt_input: dict[str, Any],
) -> dict[str, Any] | None:
    """Finalize only an engine-confirmed payment from the live mana pool."""
    if str(prompt_input.get("type") or "") != "payManaCost":
        return None
    if prompt_input.get("canConfirmFromPool") is not True:
        return None
    return {
        "type": "payManaCost",
        "output": {
            "type": "pay",
            "auto": False,
        },
    }


def _semantic_prompt_trace(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve decisions while ignoring transient empty-priority sampling."""
    canonical: list[dict[str, Any]] = []
    for raw in trace:
        item = {
            key: value
            for key, value in raw.items()
            if key not in {"snapshot", "snapshotHash"}
        }
        if item.get("forcedPass"):
            item.pop("turn", None)
            item.pop("step", None)
        canonical.append(item)
    return canonical


def _submit_traced(
    report: dict[str, Any],
    proc: subprocess.Popen[str],
    session_id: str,
    answer: dict[str, Any],
) -> None:
    report["promptTrace"][-1]["submittedAnswer"] = answer
    _submit(proc, session_id, answer)


def run_canary(args: argparse.Namespace) -> dict[str, Any]:
    kinnan_commanders, kinnan_cards = _parse_dck(
        DECK_DIR / args.deck,
        exact_kinnan_registration=True,
    )
    report: dict[str, Any] = {
        "schemaVersion": "kinnan-v9-live-forge-canary-v5",
        "pilotVersion": pilot.PILOT_VERSION,
        "policyVersion": pilot.POLICY_VERSION,
        "purpose": "component-canary",
        "rankingEvidence": False,
        "seed": args.seed,
        "status": "starting",
        "valid": False,
        "promptTrace": [],
        "registrationAudit": _registration_audit(kinnan_commanders, kinnan_cards),
    }
    stderr_path = args.report.with_suffix(".stderr.log")
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stderr_path.open("w") as stderr_file:
        proc = subprocess.Popen(
            [
                "java",
                "-Xms192m",
                "-Xmx1280m",
                "-jar",
                args.harness_jar,
                "--interactive-server",
                "--forge-home",
                args.forge_home,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            bufsize=1,
        )
        session_id = ""
        try:
            payload = {
                "gameId": f"kinnan-v9-live-canary-{args.seed}",
                "variant": "Commander",
                "startingLife": 40,
                "seed": args.seed,
                "players": [
                    _player(
                        "Kinnan pilot-v9 external",
                        args.deck,
                        ai=False,
                        exact_kinnan_registration=True,
                    ),
                    _player("RogSi AI", "RogSi_2026.dck", ai=True),
                    _player("Blue Farm AI", "Blue_Farm_2026.dck", ai=True),
                    _player("RogThras AI", "RogThras_2026.dck", ai=True),
                ],
            }
            start = json.loads(
                _rpc(
                    proc,
                    {
                        "command": "startGame",
                        "payload": json.dumps(payload, separators=(",", ":")),
                    },
                )
            )
            session_id = str(start["sessionId"])
            deadline = time.monotonic() + args.max_seconds
            last_prompt_id = None
            submitted_witness: dict[str, Any] | None = None
            action_witnesses: list[dict[str, Any]] = []
            pre_action_snapshot_hash = ""
            post_action_snapshot_hash = ""
            pre_action_material_state_hash = ""
            post_action_material_state_hash = ""
            observed_kinnan_turns: set[int] = set()
            while time.monotonic() < deadline:
                raw_prompt = _rpc(
                    proc,
                    {"command": "getPrompt", "sessionId": session_id, "playerIndex": 0},
                )
                if not raw_prompt:
                    time.sleep(0.05)
                    continue
                prompt = json.loads(raw_prompt)
                prompt_id = prompt.get("promptId")
                if prompt_id == last_prompt_id:
                    time.sleep(0.05)
                    continue
                last_prompt_id = prompt_id
                snapshot = json.loads(
                    _rpc(
                        proc,
                        {"command": "getSnapshot", "sessionId": session_id, "viewer": 0},
                    )
                )
                inp = prompt.get("input") or {}
                prompt_type = str(inp.get("type") or "")
                report["promptTrace"].append(
                    {
                        "promptId": prompt_id,
                        "promptType": prompt_type,
                        "turn": snapshot.get("turn"),
                        "step": snapshot.get("step"),
                        "presentationTitle": (inp.get("presentation") or {}).get("title"),
                        "confirmLabel": inp.get("confirmLabel"),
                        "denyLabel": inp.get("denyLabel"),
                        "promptInputHash": _stable_hash(inp),
                        # Keep the typed prompt payload in the durable raw
                        # trace. This is required to implement non-forced
                        # pilot choices from live identities and metadata.
                        "promptInput": inp,
                        # Persist the live Forge view used for this decision.
                        # Full-99 observation extraction must derive zones and
                        # transitions from engine state, never zero-fill them.
                        "snapshot": snapshot,
                        "snapshotHash": _stable_hash(snapshot),
                        "choiceMin": inp.get("min"),
                        "choiceMax": inp.get("max"),
                        "choiceCardIds": [
                            str(card.get("id") or "") if isinstance(card, dict) else ""
                            for card in list(inp.get("cards") or [])
                        ] if prompt_type == "chooseCards" else [],
                    }
                )
                horizon_turn = int(getattr(args, "horizon_turn", 0) or 0)
                horizon_kinnan_turn = int(
                    getattr(args, "horizon_kinnan_turn", 0) or 0
                )
                kinnan_horizon_reached = _kinnan_horizon_reached(
                    snapshot,
                    observed_kinnan_turns,
                    horizon_kinnan_turn,
                )
                global_horizon_reached = bool(
                    horizon_turn > 0
                    and isinstance(snapshot.get("turn"), int)
                    and snapshot.get("turn") >= horizon_turn
                )
                horizon_enabled = horizon_turn > 0 or horizon_kinnan_turn > 0
                horizon_reached = bool(
                    (horizon_kinnan_turn > 0 and kinnan_horizon_reached)
                    or (
                        horizon_kinnan_turn <= 0
                        and global_horizon_reached
                    )
                )
                horizon_reached_without_pending_action = (
                    horizon_enabled
                    and horizon_reached
                    and submitted_witness is None
                    and bool(action_witnesses)
                    and all(item.get("materialEffectConfirmed") for item in action_witnesses)
                )
                if horizon_reached_without_pending_action:
                    deterministic_witness = {
                        "actions": action_witnesses,
                        "horizonTurn": horizon_turn,
                        "horizonKinnanTurn": horizon_kinnan_turn,
                    }
                    report.update(
                        {
                            "status": "repeated_actions_applied_and_horizon_reached",
                            "valid": True,
                            "typedActionIdsComplete": True,
                            "witness": action_witnesses[0],
                            "actionWitnesses": action_witnesses,
                            "materialActionCount": len(action_witnesses),
                            "materialActionEffectConfirmed": True,
                            "boundedObservationOnly": True,
                            "repeatedPilotDecisions": len(action_witnesses) > 1,
                            "horizonTurn": horizon_turn if horizon_turn > 0 else None,
                            "horizonKinnanTurn": (
                                horizon_kinnan_turn
                                if horizon_kinnan_turn > 0
                                else None
                            ),
                            "observedKinnanTurnCount": len(observed_kinnan_turns),
                            "horizonReached": True,
                            "semanticActionTraceHash": _stable_hash(
                                _semantic_prompt_trace(report["promptTrace"])
                            ),
                            "deterministicWitnessHash": _stable_hash(deterministic_witness),
                        }
                    )
                    return report
                if submitted_witness is not None:
                    current_snapshot_hash = _stable_hash(snapshot)
                    current_material_state_hash = _stable_hash(_material_snapshot(snapshot))
                    if not post_action_snapshot_hash and current_snapshot_hash != pre_action_snapshot_hash:
                        post_action_snapshot_hash = current_snapshot_hash
                    if (
                        not post_action_material_state_hash
                        and current_material_state_hash != pre_action_material_state_hash
                    ):
                        post_action_material_state_hash = current_material_state_hash
                    submitted_turn = submitted_witness["snapshotTurn"]
                    submitted_step = submitted_witness["snapshotStep"]
                    phase_advanced = (
                        snapshot.get("turn") != submitted_turn
                        or snapshot.get("step") != submitted_step
                    )
                    choose_action_ready = (
                        prompt_type == "chooseAction"
                        and bool(list(inp.get("actions") or []))
                    )
                    action_resolution_boundary = (
                        phase_advanced or choose_action_ready
                    )
                    if post_action_material_state_hash and action_resolution_boundary:
                        transition = {
                            "fromPromptId": submitted_witness["promptId"],
                            "toPromptId": prompt_id,
                            "fromTurn": submitted_turn,
                            "fromStep": submitted_step,
                            "toTurn": snapshot.get("turn"),
                            "toStep": snapshot.get("step"),
                        }
                        submitted_witness["materialEffectConfirmed"] = True
                        submitted_witness["transition"] = transition
                        deterministic_witness = {
                            "actions": action_witnesses,
                            "horizonTurn": horizon_turn,
                            "horizonKinnanTurn": horizon_kinnan_turn,
                        }
                        action_horizon_reached = (
                            not horizon_enabled or horizon_reached
                        )
                        report.update(
                            {
                                "status": (
                                    "typed_action_applied_and_horizon_reached"
                                    if action_horizon_reached
                                    else "typed_action_applied_bounded_observation_continuing"
                                ),
                                "valid": action_horizon_reached,
                                "typedActionIdsComplete": True,
                                "witness": action_witnesses[0],
                                "actionWitnesses": action_witnesses,
                                "materialActionCount": len(action_witnesses),
                                "transition": transition,
                                "preActionSnapshotHash": pre_action_snapshot_hash,
                                "postActionSnapshotHash": post_action_snapshot_hash,
                                "preActionMaterialStateHash": pre_action_material_state_hash,
                                "postActionMaterialStateHash": post_action_material_state_hash,
                                "materialActionEffectConfirmed": True,
                                "boundedObservationOnly": horizon_enabled,
                                "repeatedPilotDecisions": len(action_witnesses) > 1,
                                "horizonTurn": horizon_turn if horizon_turn > 0 else None,
                                "horizonKinnanTurn": (
                                    horizon_kinnan_turn
                                    if horizon_kinnan_turn > 0
                                    else None
                                ),
                                "observedKinnanTurnCount": len(observed_kinnan_turns),
                                "horizonReached": action_horizon_reached,
                                "semanticActionTraceHash": _stable_hash(
                                    _semantic_prompt_trace(report["promptTrace"])
                                ),
                                "deterministicWitnessHash": _stable_hash(deterministic_witness),
                            }
                        )
                        if action_horizon_reached:
                            return report
                        submitted_witness = None
                        pre_action_snapshot_hash = ""
                        post_action_snapshot_hash = ""
                        pre_action_material_state_hash = ""
                        post_action_material_state_hash = ""
                if prompt_type == "chooseAction":
                    actions = list(inp.get("actions") or [])
                    if not actions:
                        report["promptTrace"][-1]["actionCount"] = 0
                        report["promptTrace"][-1]["forcedPass"] = True
                        report["emptyActionPrompts"] = int(report.get("emptyActionPrompts") or 0) + 1
                        _submit_traced(
                            report,
                            proc,
                            session_id,
                            {
                                "type": "chooseAction",
                                "output": {"type": "pass", "exhaustStack": False},
                            },
                        )
                        continue
                    max_typed_actions = int(getattr(args, "max_typed_actions", 1) or 1)
                    if submitted_witness is None and len(action_witnesses) >= max_typed_actions:
                        report["promptTrace"][-1]["actionCount"] = len(actions)
                        report["promptTrace"][-1]["maxActionPass"] = True
                        _submit_traced(
                            report,
                            proc,
                            session_id,
                            {
                                "type": "chooseAction",
                                "output": {"type": "pass", "exhaustStack": False},
                            },
                        )
                        continue
                    if submitted_witness is not None:
                        report["promptTrace"][-1]["actionCount"] = len(actions)
                        report["promptTrace"][-1]["boundedPass"] = True
                        _submit_traced(
                            report,
                            proc,
                            session_id,
                            {
                                "type": "chooseAction",
                                "output": {"type": "pass", "exhaustStack": False},
                            },
                        )
                        continue
                    action_ids = [str(action.get("actionId") or action.get("id") or "") for action in actions]
                    if not all(action_ids) or len(set(action_ids)) != len(action_ids):
                        raise RuntimeError("live Forge actions lack unique stable action identity")
                    chosen = pilot.choose_action(
                        actions,
                        snapshot,
                        player_id=str(prompt.get("decidingPlayerId") or "player-0"),
                    )
                    if chosen is None:
                        report["promptTrace"][-1]["actionCount"] = len(actions)
                        report["promptTrace"][-1]["policyPass"] = True
                        _submit_traced(
                            report,
                            proc,
                            session_id,
                            {
                                "type": "chooseAction",
                                "output": {
                                    "type": "pass",
                                    "exhaustStack": False,
                                },
                            },
                        )
                        continue
                    chosen_id = str(chosen.get("actionId") or chosen.get("id") or "")
                    if chosen_id not in set(action_ids):
                        raise RuntimeError("pilot-v9 selected an action outside the live legal set")
                    witness = {
                        "promptId": prompt_id,
                        "promptType": prompt_type,
                        "actionCount": len(actions),
                        "actionIds": action_ids,
                        "chosenActionId": chosen_id,
                        "chosenActionLabel": str(chosen.get("label") or ""),
                        "chosenActionType": str(chosen.get("type") or ""),
                        "chosenActionDescription": str(chosen.get("description") or ""),
                        "chosenActionCost": str(chosen.get("cost") or ""),
                        "chosenActionCardId": str(chosen.get("cardId") or ""),
                        "snapshotTurn": snapshot.get("turn"),
                        "snapshotStep": snapshot.get("step"),
                        "priorityPlayerId": snapshot.get("priorityPlayerId"),
                    }
                    pre_action_snapshot_hash = _stable_hash(snapshot)
                    pre_action_material_state_hash = _stable_hash(_material_snapshot(snapshot))
                    submitted_witness = witness
                    action_witnesses.append(witness)
                    report.update(
                        {
                            "status": "typed_action_submitted",
                            "typedActionIdsComplete": True,
                            "witness": action_witnesses[0],
                            "actionWitnesses": action_witnesses,
                        }
                    )
                    _submit_traced(
                        report,
                        proc,
                        session_id,
                        {
                            "type": "chooseAction",
                            "output": {"type": "act", "actionId": chosen_id},
                        },
                    )
                    continue

                answer = _chosen_cost_confirmation(inp, submitted_witness)
                if answer is None:
                    answer = _chosen_optional_entry_payment(inp, submitted_witness)
                if answer is None:
                    answer = _chosen_action_card_selection(inp, submitted_witness)
                if answer is None:
                    answer = _pay_mana_cost_answer(inp)
                if answer is None:
                    answer = _pregame_answer(inp)
                if answer is None:
                    context = "after typed action" if submitted_witness is not None else "before typed action"
                    raise RuntimeError(
                        f"unsupported prompt {context}: {prompt_type!r}"
                    )
                _submit_traced(report, proc, session_id, answer)
            if submitted_witness is not None:
                raise RuntimeError("timed out before the submitted action caused material Forge state change and phase advance")
            raise RuntimeError("timed out before a live typed chooseAction prompt")
        except Exception as exc:
            # Preserve the complete live prompt trace before propagating the
            # fail-closed error to the qualification orchestrator.
            report["status"] = "failed_closed"
            report["valid"] = False
            report["error"] = repr(exc)
            raise
        finally:
            disposal_mode = "terminate"
            disposal_confirmed = False
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                disposal_mode = "kill"
                proc.kill()
                proc.wait(timeout=10)
            disposal_confirmed = proc.poll() is not None
            report["jvmDisposal"] = {
                "mode": disposal_mode,
                "confirmed": disposal_confirmed,
                "returnCode": proc.returncode,
            }
            if not disposal_confirmed:
                report["status"] = "failed_closed"
                report["valid"] = False
                report["error"] = "Forge JVM disposal was not confirmed"
            if not report.get("valid"):
                # A failed component run is still a durable diagnostic result.
                # Flush stderr and retain the structured prompt/action trace so
                # the next semantic repair is evidence-based.
                stderr_file.flush()
                stderr_text = (
                    stderr_path.read_text(errors="replace")
                    if stderr_path.exists()
                    else ""
                )
                unsupported = _unsupported_card_names(stderr_text)
                report["cardResolution"] = {
                    "unsupportedCount": len(unsupported),
                    "unsupportedRegisteredOrEngineNames": unsupported,
                    "valid": not unsupported,
                }
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(
                    json.dumps(report, indent=2, sort_keys=True) + "\n"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical pilot-v9 live Forge component canary")
    parser.add_argument("harness_jar")
    parser.add_argument("forge_home")
    parser.add_argument(
        "--deck",
        default="Kinnan_Sterling_TopDeck_Invitational_2026.dck",
    )
    parser.add_argument("--seed", type=int, default=1999000)
    parser.add_argument("--max-seconds", type=int, default=90)
    parser.add_argument(
        "--horizon-turn",
        type=int,
        default=0,
        help="continue component observation until this global Forge turn",
    )
    parser.add_argument(
        "--horizon-kinnan-turn",
        type=int,
        default=0,
        help="continue through the end of this player-0 turn",
    )
    parser.add_argument(
        "--max-typed-actions",
        type=int,
        default=1,
        help="maximum pilot-v9 typed actions before pass-only continuation",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_canary(args)
    except Exception as exc:
        report = {
            "schemaVersion": "kinnan-v9-live-forge-canary-v4",
            "pilotVersion": pilot.PILOT_VERSION,
            "policyVersion": pilot.POLICY_VERSION,
            "purpose": "component-canary",
            "rankingEvidence": False,
            "seed": args.seed,
            "status": "failed_closed",
            "valid": False,
            "error": repr(exc),
        }
    stderr_path = args.report.with_suffix(".stderr.log")
    stderr_text = stderr_path.read_text(errors="replace") if stderr_path.exists() else ""
    unsupported = _unsupported_card_names(stderr_text)
    report["cardResolution"] = {
        "unsupportedCount": len(unsupported),
        "unsupportedRegisteredOrEngineNames": unsupported,
        "valid": not unsupported,
    }
    if unsupported:
        report["status"] = "failed_closed"
        report["valid"] = False
        report["error"] = "Forge did not resolve every registered deck card"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
