#!/usr/bin/env python3
"""Forge-backed external cEDH pilot, engineering-gate version 8.

Forge remains the rules/legality authority.  This runner only chooses action IDs
advertised by Manabrew and records the final GameViewDto winnerId.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import manabrew_pilot as base
import manabrew_pilot_v3 as v3
import manabrew_pilot_v7 as v7
import manabrew_pilot_v5 as v5
import kinnan_policy_v8 as policy


PILOT_VERSION = "v8.3.0"
CURRENT_KINNAN_SEAT = 0
_COLOR_SAFE_RESPONSE = base.response_for
_ORIGINAL_TARGET_SCORE = base.kinnan_target_score

FLEX_BLUE = {"Hydroelectric Specimen", "Sink into Stupor"}
ONE_G_DORKS = {
    "Birds of Paradise",
    "Delighted Halfling",
    "Elvish Mystic",
    "Fyndhorn Elves",
    "Llanowar Elves",
}

BASE_POD = [
    ("Kinnan", "Kinnan_TestB.dck"),
    ("RogSi", "RogSi_2026.dck"),
    ("Blue Farm", "Blue_Farm_2026.dck"),
    ("RogThras", "RogThras_2026.dck"),
]

VARIANT_FILES = {
    "B0": "Kinnan_TestB.dck",
    "B2": "Kinnan_B2_Turbo_Deterministic.dck",
}

base.LANDS.update({"Shifting Woodland", "Verdant Catacombs"})
base.FAST_MANA.update({"Fellwar Stone"})


def _infinite_at(snapshot: dict[str, Any], seat: int) -> bool:
    battlefield = policy.names_in(snapshot, seat, "battlefield")
    return any(
        pieces <= battlefield
        for pieces in (
            {"Kinnan, Bonder Prodigy", "Basalt Monolith"},
            {"Grim Monolith", "Power Artifact"},
            {"Kinnan, Bonder Prodigy", "Grim Monolith", "Forensic Gadgeteer"},
        )
    )


def _dynamic_infinite(snapshot: dict[str, Any]) -> bool:
    return _infinite_at(snapshot, CURRENT_KINNAN_SEAT)


# v5/v7 were written when Kinnan was permanently player-0.  Keep their useful
# scoring but point their combo predicates at the current rotated seat.
v5._infinite_kinnan = _dynamic_infinite
v7._is_combo_infinite = _dynamic_infinite


def _mana_profile(names: list[str]) -> tuple[list[str], bool, bool, int]:
    lands = [name for name in names if name in base.LANDS or name in FLEX_BLUE]
    names_set = set(names)
    both = set(v5.LAND_ANY) | set(v5.FETCHES)
    has_green = any(name in v5.LAND_G for name in lands)
    has_blue = any(name in v5.LAND_U or name in FLEX_BLUE for name in lands)
    if any(name in both for name in lands):
        has_green = has_blue = True
    if "Lotus Petal" in names_set:
        has_green = has_blue = True
    if "Mox Diamond" in names_set and len(lands) >= 2:
        has_green = has_blue = True
    chrome_ok = "Chrome Mox" in names_set and any(
        name not in base.LANDS
        and name not in FLEX_BLUE
        and name not in base.FAST_MANA
        and name not in {"Walking Ballista", "Staff of Domination"}
        for name in names_set
    )
    if chrome_ok and (has_green or has_blue):
        has_green = has_blue = True
    dorks = sum(name in ONE_G_DORKS for name in names) if has_green else 0
    rocks = sum(
        name in base.FAST_MANA and name not in ONE_G_DORKS and name not in base.LANDS
        for name in names
    )
    return lands, has_green, has_blue, len(lands) + dorks + rocks


def keep_hand_v8(deck: str, hand: list[dict[str, Any]], mulligan_count: int) -> bool:
    if deck != "Kinnan":
        return v7._phase_keep(deck, hand, mulligan_count)
    names = [base.card_name(card) for card in hand]
    names_set = set(names)
    lands, has_green, has_blue, sources = _mana_profile(names)
    if not lands:
        return False if mulligan_count < 4 else sources >= 2

    plan = bool(
        names_set
        & (
            base.K_TUTORS
            | v5.K_ENGINES
            | v5.K_DRAW
            | {"Basalt Monolith", "Grim Monolith", "Power Artifact", "Mystic Remora", "Rhystic Study", "Sylvan Library"}
        )
    )
    interaction = bool(names_set & (policy.TRUE_COUNTERS | policy.SELF_PROTECTION))
    combo_access = bool(
        names_set
        & (
            v7.BASALT_TUTORS
            | {"Basalt Monolith", "Grim Monolith", "Power Artifact", "Tezzeret the Seeker"}
        )
    )
    draw = bool(names_set & (v5.K_DRAW | {"Sylvan Library"}))
    score = sum(base.hand_score("Kinnan", name) for name in names)
    if mulligan_count == 0:
        return has_green and has_blue and sources >= 2 and plan and score >= 30 and (combo_access or interaction or draw)
    if mulligan_count == 1:
        return has_green and has_blue and sources >= 2 and plan and score >= 25 and (combo_access or interaction or draw)
    if mulligan_count == 2:
        return has_green and has_blue and sources >= 2 and plan and score >= 18
    return has_green and has_blue and sources >= 2 and (plan or interaction)


def _keep_priority(name: str) -> int:
    if name in set(v5.LAND_ANY) | set(v5.FETCHES):
        return 120
    if name in v5.LAND_G or name in v5.LAND_U:
        return 105
    if name in FLEX_BLUE:
        return 88
    if name in base.LANDS:
        return 72
    if name == "Basalt Monolith":
        return 118
    if name in v7.BASALT_TUTORS | {"Tezzeret the Seeker"}:
        return 110
    if name in {"Kinnan, Bonder Prodigy", "Power Artifact", "Grim Monolith"}:
        return 102
    if name == "Mystic Remora":
        return 98
    if name in policy.TRUE_COUNTERS | policy.SELF_PROTECTION:
        return 90
    if name in ONE_G_DORKS:
        return 86
    if name in base.FAST_MANA:
        return 84
    if name in {"Bloom Tender", "Forensic Gadgeteer"}:
        return 78
    if name in policy.OUTLETS:
        return 70
    return 30 + base.hand_score("Kinnan", name)


base.keep_hand = keep_hand_v8


def configure_decks(variant: str, kinnan_seat: int) -> list[tuple[str, str]]:
    global CURRENT_KINNAN_SEAT
    if variant not in VARIANT_FILES:
        raise ValueError(f"unknown variant {variant}")
    if kinnan_seat not in range(4):
        raise ValueError(f"invalid Kinnan seat {kinnan_seat}")
    CURRENT_KINNAN_SEAT = kinnan_seat
    opponents = list(BASE_POD[1:])
    ordered = opponents[:]
    ordered.insert(kinnan_seat, ("Kinnan", VARIANT_FILES[variant]))
    base.DECKS = ordered
    v3.DECKS = ordered
    return ordered


def _action_card(action: dict[str, Any], snapshot: dict[str, Any]) -> str:
    card_id = action.get("cardId") or action.get("card_id")
    return policy.card_name(base.all_visible_cards(snapshot).get(card_id, {}))


def v8_action_score(deck: str, action: dict[str, Any], snapshot: dict[str, Any], player: int) -> int:
    score = v7.v7_action_score(deck, action, snapshot, player)
    if deck != "Kinnan":
        return score

    name = _action_card(action, snapshot)
    action_type = action.get("type")
    own_turn = snapshot.get("activePlayerId") == f"player-{player}"
    own_main = own_turn and snapshot.get("step") in {"main1", "main2"}
    stack_text = json.dumps(snapshot.get("stack", []) or []).lower()
    battlefield = policy.names_in(snapshot, player, "battlefield")
    pool = base.mana_total(snapshot, player)
    infinite = {"Kinnan, Bonder Prodigy", "Basalt Monolith"} <= battlefield

    if infinite and action_type == "activateAbility":
        description = str(action.get("description") or "").lower()
        if name == "Basalt Monolith":
            if pool < 7:
                if "untap" in description and pool >= 3:
                    return 4200
                if action.get("isManaAbility") or "add" in description:
                    return 4190
            return -4000
        if name == "Kinnan, Bonder Prodigy":
            return 5000 if pool >= 7 else -1500
        if name == "Thrasios, Triton Hero":
            return 5200 if pool >= 4 else -1500
        if name == "Staff of Domination":
            return 5150 if pool >= 5 else -1500
    if infinite and action_type == "cast" and name in policy.OUTLETS:
        return 5050

    if action_type == "cast" and name == "Borne Upon a Wind":
        # Borne is a flash enabler, not a counterspell.  Do not spend it as if it
        # answered an opponent's stack object.
        return 450 if own_main or _infinite_at(snapshot, player) else -1800
    if action_type == "cast" and name == "Veil of Summer":
        protected = any(token in stack_text for token in ("counter", "target", "blue", "black"))
        return 1875 if protected else -1500
    if action_type == "cast" and name in policy.TRUE_COUNTERS:
        return 1925 if stack_text else 100
    if action_type == "cast" and name == "Defense Grid":
        return 1375 if own_main and not snapshot.get("stack") else -1000
    if action_type == "cast" and name in {"Tezzeret the Seeker", "Fabricate", "Transmute Artifact", "Whir of Invention"}:
        return 2010 if "Kinnan, Bonder Prodigy" in battlefield and "Basalt Monolith" not in battlefield else 1225
    if action_type == "cast" and name in {"The One Ring", "Mystic Remora", "Rhystic Study", "Sylvan Library"}:
        return 1210
    return score


base.action_score = v8_action_score


def target_score_v8(name: str, snapshot: dict[str, Any]) -> int:
    battlefield = policy.names_in(snapshot, CURRENT_KINNAN_SEAT, "battlefield")
    if {"Kinnan, Bonder Prodigy", "Basalt Monolith"} <= battlefield:
        if name == "Thrasios, Triton Hero":
            return 10000
        if name == "Staff of Domination":
            return 9500
        if name == "Walking Ballista":
            return 200
    if "Kinnan, Bonder Prodigy" in battlefield and name == "Basalt Monolith":
        return 9000
    static = {
        "Basalt Monolith": 120,
        "Grim Monolith": 90,
        "Power Artifact": 80,
        "Staff of Domination": 78,
        "Walking Ballista": 76,
        "Thrasios, Triton Hero": 74,
        "Moonsilver Key": 70,
        "Forensic Gadgeteer": 68,
    }
    return static.get(name, base.hand_score("Kinnan", name))


base.kinnan_target_score = target_score_v8


def smart_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    inp = prompt.get("input") or {}
    prompt_type = inp.get("type")
    combo_ready = _infinite_at(snapshot, CURRENT_KINNAN_SEAT)

    if deck == "Kinnan" and prompt_type == "mulliganPutBack":
        hand = base.zone_cards(snapshot, player, "hand")
        count = int(inp.get("count", inp.get("cardsToReturn", 0)) or 0)
        ranked = sorted(hand, key=lambda card: _keep_priority(base.card_name(card)))
        card_ids = [card.get("id") for card in ranked[:count] if card.get("id")]
        return {
            "type": "mulliganPutBack",
            "output": {"type": "mulliganPutBackDecision", "cardIds": card_ids},
        }

    if prompt_type == "chooseAttackers":
        assignments = policy.choose_attackers(inp, snapshot, player, deck)
        return {
            "type": "chooseAttackers",
            "output": {"type": "declareAttackers", "assignments": assignments},
        }
    if prompt_type == "chooseBlockers":
        assignments = policy.choose_blockers(inp, snapshot, player, deck)
        return {
            "type": "chooseBlockers",
            "output": {"type": "declareBlockers", "assignments": assignments},
        }
    if prompt_type == "chooseBoolean":
        value = policy.choose_boolean(inp, deck, combo_ready)
        return {"type": "chooseBoolean", "output": {"type": "decision", "value": value}}
    if prompt_type == "chooseFromSelection":
        chosen = policy.choose_selection(inp, deck)
        return {
            "type": "chooseFromSelection",
            "output": {"type": "selectionDecision", "chosenIndices": chosen},
        }
    return _COLOR_SAFE_RESPONSE(prompt, snapshot, deck, player)


base.response_for = smart_response


def choose_productive_payment_v8(inp: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    disposition, action_id = policy.choose_payment_action(inp)
    if disposition == "confirm":
        return {"type": "payManaCost", "output": {"type": "pay", "auto": False}}, False
    if disposition == "act" and action_id:
        return {
            "type": "payManaCost",
            "output": {"type": "act", "actionId": action_id},
        }, False
    return {"type": "payManaCost", "output": {"type": "cancel"}}, True


def _chosen_action(inp: dict[str, Any], answer: dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        action_id = answer["output"]["actionId"]
    except (KeyError, TypeError):
        return None
    return next((action for action in inp.get("actions", []) or [] if action.get("id") == action_id), None)


def _is_attempt_action(
    line: str | None, action: dict[str, Any] | None, snapshot: dict[str, Any], kinnan_seat: int
) -> bool:
    if not line or not action:
        return False
    name = _action_card(action, snapshot)
    return action.get("type") == "activateAbility" or name in (
        policy.OUTLETS
        | {"Basalt Monolith", "Grim Monolith", "Power Artifact", "Forensic Gadgeteer"}
    )


def run_game(
    jar: str,
    forge_home: str,
    seed: int,
    variant: str,
    kinnan_seat: int,
    max_prompts: int = 3500,
    max_round: int = 8,
    max_seconds: int = 180,
) -> dict[str, Any]:
    decks = configure_decks(variant, kinnan_seat)
    deck_hashes = [
        hashlib.sha256((base.DECK_DIR / filename).read_bytes()).hexdigest()
        for _, filename in decks
    ]
    trace: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    failed_cast_states: set[tuple[Any, ...]] = set()
    attempted_action_states: set[tuple[str, int, str]] = set()
    opening_hands: dict[str, list[str]] = {}
    kept_hands: dict[str, list[str]] = {}
    mulligans: dict[str, int] = {str(index): 0 for index in range(4)}
    started = time.monotonic()

    proc = subprocess.Popen(
        ["java", "-Xmx4g", "-jar", jar, "--interactive-server", "--forge-home", forge_home],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    final_snapshot: dict[str, Any] = {}
    try:
        payload = {
            "gameId": f"cedh-v8-{variant}-{seed}-s{kinnan_seat}",
            "variant": "Commander",
            "startingLife": 40,
            "seed": seed,
            "players": base.build_players(),
        }
        start = json.loads(
            base.rpc(proc, {"command": "startGame", "payload": json.dumps(payload, separators=(",", ":"))})
        )
        session_id = start["sessionId"]
        last_prompt_id = None
        last_progress_at = time.monotonic()
        result: dict[str, Any] = {
            "pilotVersion": PILOT_VERSION,
            "variant": variant,
            "seed": seed,
            "kinnanSeat": kinnan_seat,
            "seatDecks": [name for name, _ in decks],
            "seatDeckSha256s": deck_hashes,
            "variantDeckSha256": deck_hashes[kinnan_seat],
            "status": "prompt_limit",
            "winnerSeat": None,
            "kinnanWon": False,
            "firstAssemblyTurn": None,
            "firstAttemptTurn": None,
            "protectedAttempt": False,
            "attemptResolved": False,
            "comboLine": None,
            "protectionAvailable": [],
            "globalTurn": None,
            "round": 0,
            "prompts": 0,
        }

        while result["prompts"] < max_prompts:
            if time.monotonic() - started > max_seconds:
                result["status"] = "wall_timeout"
                break
            raw = base.rpc(proc, {"command": "getPrompt", "sessionId": session_id, "playerIndex": 0})
            if not raw:
                if time.monotonic() - last_progress_at > 60:
                    result["status"] = "idle_timeout"
                    break
                time.sleep(0.01)
                continue
            prompt = json.loads(raw)
            prompt_id = prompt.get("promptId")
            if prompt_id == last_prompt_id:
                if time.monotonic() - last_progress_at > 60:
                    result["status"] = "stale_prompt_timeout"
                    break
                time.sleep(0.01)
                continue
            last_progress_at = time.monotonic()
            last_prompt_id = prompt_id

            deciding = prompt.get("decidingPlayerId") or "player-0"
            player = policy.player_index(deciding)
            if player is None or not 0 <= player < 4:
                player = 0
            deck = decks[player][0]
            snapshot = json.loads(
                base.rpc(proc, {"command": "getSnapshot", "sessionId": session_id, "viewer": player})
            )
            final_snapshot = snapshot
            global_turn = snapshot.get("turn")
            round_number = v3.round_from_global_turn(global_turn)
            result["globalTurn"] = global_turn
            result["round"] = round_number
            if round_number > max_round:
                # The primary endpoint is defined at the end of Kinnan T4.
                # Beginning the next pod round means the complete fixed
                # observation horizon was seen, even if the pod had no natural
                # game winner.  Pod wins remain exclusive to game_over.
                result["status"] = "horizon_complete"
                break

            inp = prompt.get("input") or {}
            prompt_type = inp.get("type")
            hand = [policy.card_name(card) for card in base.zone_cards(snapshot, player, "hand")]
            if str(player) not in opening_hands and prompt_type == "mulligan":
                opening_hands[str(player)] = hand
            if prompt_type == "mulligan":
                mulligans[str(player)] = max(
                    mulligans[str(player)], int(inp.get("mulliganCount", 0) or 0)
                )
            if (
                str(player) not in kept_hands
                and hand
                and prompt_type not in {"mulligan", "mulliganPutBack"}
            ):
                kept_hands[str(player)] = hand

            line = policy.deterministic_line(snapshot, kinnan_seat)
            if line and result["firstAssemblyTurn"] is None:
                result["firstAssemblyTurn"] = round_number
                result["comboLine"] = line

            state_hash = policy.visible_state_hash(snapshot)
            answer = None
            canceled_unpayable = False
            try:
                if prompt_type == "payManaCost":
                    answer, canceled_unpayable = choose_productive_payment_v8(inp)
                    if canceled_unpayable and inp.get("cardId"):
                        failed_cast_states.add(
                            (global_turn, snapshot.get("step"), player, inp.get("cardId"))
                        )
                elif prompt_type == "chooseAction":
                    filtered = []
                    for action in inp.get("actions", []) or []:
                        cast_key = (global_turn, snapshot.get("step"), player, action.get("cardId"))
                        action_key = (state_hash, player, str(action.get("id") or ""))
                        if action.get("type") == "cast" and cast_key in failed_cast_states:
                            continue
                        if action_key in attempted_action_states:
                            continue
                        filtered.append(action)
                    patched_prompt = dict(prompt)
                    patched_input = dict(inp)
                    patched_input["actions"] = filtered
                    patched_prompt["input"] = patched_input
                    answer = base.response_for(patched_prompt, snapshot, deck, player)
                else:
                    answer = base.response_for(prompt, snapshot, deck, player)
            except Exception as exc:
                errors.append(
                    {"player": player, "deck": deck, "prompt": prompt, "error": repr(exc)}
                )
                result["status"] = "unsupported_prompt"
                result["error"] = repr(exc)
                break

            chosen = _chosen_action(inp, answer) if prompt_type == "chooseAction" else None
            if chosen:
                attempted_action_states.add((state_hash, player, str(chosen.get("id") or "")))
            if player == kinnan_seat and result["firstAttemptTurn"] is None:
                if _is_attempt_action(line, chosen, snapshot, kinnan_seat):
                    result["firstAttemptTurn"] = round_number
                    available = policy.protection_available(snapshot, kinnan_seat)
                    result["protectionAvailable"] = available
                    result["protectedAttempt"] = bool(available) or "Defense Grid" in policy.names_in(
                        snapshot, kinnan_seat, "battlefield"
                    )

            actions = inp.get("actions", []) or [] if prompt_type == "chooseAction" else []
            trace.append(
                {
                    "seq": result["prompts"],
                    "promptId": prompt_id,
                    "player": player,
                    "deck": deck,
                    "globalTurn": global_turn,
                    "round": round_number,
                    "step": snapshot.get("step"),
                    "activePlayerId": snapshot.get("activePlayerId"),
                    "priorityPlayerId": snapshot.get("priorityPlayerId"),
                    "stateHash": state_hash,
                    "legalActionHash": policy.legal_action_hash(actions),
                    "legalActionCount": len(actions),
                    "prompt": v3.summarize_prompt(inp),
                    "answer": answer,
                    "chosenCard": _action_card(chosen, snapshot) if chosen else None,
                    "comboLine": line,
                    "canceledUnpayable": canceled_unpayable,
                }
            )
            result["prompts"] += 1
            if result["prompts"] >= max_prompts:
                result["status"] = "prompt_cap"
                break

            if prompt_type == "gameOver" or snapshot.get("gameOver"):
                result["status"] = "game_over"
                result["winnerSeat"] = policy.authoritative_winner(snapshot)
                break
            if answer is not None:
                base.rpc(
                    proc,
                    {
                        "command": "submitAction",
                        "sessionId": session_id,
                        "payload": json.dumps(answer, separators=(",", ":")),
                    },
                )

        if final_snapshot.get("gameOver"):
            result["winnerSeat"] = policy.authoritative_winner(final_snapshot)
        result["kinnanWon"] = result["winnerSeat"] == kinnan_seat
        result["attemptResolved"] = bool(result["kinnanWon"] and result["firstAttemptTurn"] is not None)
        result["deterministicT3"] = bool(
            result["firstAssemblyTurn"] is not None and result["firstAssemblyTurn"] <= 3
        )
        result["deterministicT4"] = bool(
            result["firstAssemblyTurn"] is not None and result["firstAssemblyTurn"] <= 4
        )
        result["mulligans"] = mulligans
        result["openingHands"] = opening_hands
        result["keptHands"] = kept_hands
        result["wallMs"] = round((time.monotonic() - started) * 1000)
        result["primaryFailureCode"] = policy.primary_failure(result)

        suffix = f"{variant}-{seed}-s{kinnan_seat}"
        if errors:
            (base.RESULT_DIR / f"pilot-errors-{suffix}.json").write_text(json.dumps(errors, indent=2))
        (base.RESULT_DIR / f"pilot-trace-{suffix}.json").write_text(json.dumps(trace, indent=2))
        (base.RESULT_DIR / f"pilot-result-{suffix}.json").write_text(json.dumps(result, indent=2))
        return result
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        stderr = proc.stderr.read() if proc.stderr else ""
        if stderr:
            suffix = f"{variant}-{seed}-s{kinnan_seat}"
            (base.RESULT_DIR / f"pilot-stderr-{suffix}.log").write_text(stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("harness_jar")
    parser.add_argument("forge_home")
    parser.add_argument("--variant", choices=sorted(VARIANT_FILES), required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[101])
    parser.add_argument("--seat-offset", type=int, default=0)
    parser.add_argument("--max-round", type=int, default=4)
    parser.add_argument("--max-prompts", type=int, default=3500)
    parser.add_argument("--max-seconds", type=int, default=180)
    args = parser.parse_args()

    results = []
    for index, seed in enumerate(args.seeds):
        kinnan_seat = (args.seat_offset + index) % 4
        try:
            result = run_game(
                args.harness_jar,
                args.forge_home,
                seed,
                args.variant,
                kinnan_seat,
                max_prompts=args.max_prompts,
                max_round=args.max_round,
                max_seconds=args.max_seconds,
            )
        except Exception as exc:
            result = {
                "pilotVersion": PILOT_VERSION,
                "variant": args.variant,
                "seed": seed,
                "kinnanSeat": kinnan_seat,
                "status": "crash",
                "error": repr(exc),
                "primaryFailureCode": "ENGINE_ERROR",
            }
        print(json.dumps(result, sort_keys=True), flush=True)
        results.append(result)

    path = base.RESULT_DIR / f"pilot-summary-{args.variant}.json"
    path.write_text(json.dumps(results, indent=2))
    completed = {"game_over", "horizon_complete"}
    return 0 if all(item.get("status") in completed for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
