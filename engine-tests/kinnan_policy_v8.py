"""Pure policy and measurement helpers for the Forge/Manabrew v8 pilot.

This module deliberately has no dependency on Forge or the legacy pilot modules so
that the protocol-critical decisions can be unit tested before a JVM game starts.
"""

from __future__ import annotations

import hashlib
import json
import re
from itertools import product
from typing import Any, Iterable


TRUE_COUNTERS = {
    "An Offer You Can't Refuse",
    "Dispel",
    "Fierce Guardianship",
    "Flusterstorm",
    "Force of Negation",
    "Force of Will",
    "Mental Misstep",
    "Mindbreak Trap",
    "Pact of Negation",
    "Swan Song",
}

SELF_PROTECTION = {
    "Defense Grid",
    "Misdirection",
    "Veil of Summer",
}

FLASH_ENABLERS = {"Borne Upon a Wind", "Valley Floodcaller"}

OUTLETS = {
    "Energy Refractor",
    "Staff of Domination",
    "Thrasios, Triton Hero",
    "Walking Ballista",
}

ENGINE_CREATURES = {
    "Bloom Tender",
    "Devoted Druid",
    "Forensic Gadgeteer",
    "Kinnan, Bonder Prodigy",
    "Thrasios, Triton Hero",
}

TURN_STEPS = (
    "untap",
    "upkeep",
    "draw",
    "main1",
    "combatBegin",
    "combatDeclareAttackers",
    "combatDeclareBlockers",
    "combatFirstStrikeDamage",
    "combatDamage",
    "combatEnd",
    "main2",
    "endOfTurn",
    "cleanup",
)

MONOLITHS = {"Basalt Monolith", "Grim Monolith"}


def card_name(card: dict[str, Any] | None) -> str:
    return str(((card or {}).get("identity") or {}).get("name") or "")


def player_index(player_id: Any) -> int | None:
    try:
        return int(str(player_id).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return None


def zone_cards(snapshot: dict[str, Any], player: int, zone: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in snapshot.get("zones", []) or []:
        if item.get("ownerId") == f"player-{player}" and item.get("zone") == zone:
            cards.extend(item.get("cards", []) or [])
    return cards


def card_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for item in snapshot.get("zones", []) or []:
        for card in item.get("cards", []) or []:
            if card.get("id"):
                mapped[str(card["id"])] = card
    return mapped


def names_in(snapshot: dict[str, Any], player: int, zone: str) -> set[str]:
    return {card_name(card) for card in zone_cards(snapshot, player, zone)}


def authoritative_winner(snapshot: dict[str, Any]) -> int | None:
    """Return the authoritative winner seat from GameViewDto, or None for a draw."""

    if not snapshot.get("gameOver"):
        return None
    return player_index(snapshot.get("winnerId"))


def deterministic_line(snapshot: dict[str, Any], kinnan_seat: int) -> str | None:
    """Recognize resolved, deterministic engine states using visible information."""

    battlefield = names_in(snapshot, kinnan_seat, "battlefield")
    hand = names_in(snapshot, kinnan_seat, "hand")
    available = battlefield | hand

    if {"Kinnan, Bonder Prodigy", "Basalt Monolith"} <= battlefield:
        if available & OUTLETS:
            return "Kinnan + Basalt + deterministic outlet"
        # Both locked lists contain Thrasios and Ballista. Infinite colorless can
        # activate Kinnan through every finite top-five block until Thrasios is
        # found, then Thrasios draws Ballista for a lethal cast. This is not a
        # one-shot random Kinnan hit: the finite library is exhaustively covered.
        return "Kinnan + Basalt -> exhaustive Kinnan activations -> Thrasios -> Ballista"

    if {"Kinnan, Bonder Prodigy", "Grim Monolith", "Power Artifact"} <= battlefield:
        return "Kinnan + Grim + Power Artifact -> exhaustive Kinnan activations -> Thrasios -> Ballista"

    if {"Grim Monolith", "Power Artifact"} <= battlefield:
        if available & OUTLETS:
            return "Grim Monolith + Power Artifact + deterministic outlet"

    if {"Basalt Monolith", "Power Artifact"} <= battlefield:
        if available & OUTLETS:
            return "Basalt Monolith + Power Artifact + deterministic outlet"

    if {"Kinnan, Bonder Prodigy", "Grim Monolith", "Forensic Gadgeteer"} <= battlefield:
        return "Kinnan + Grim + Forensic Gadgeteer -> exhaustive Kinnan activations -> Thrasios -> Ballista"

    for card in zone_cards(snapshot, kinnan_seat, "battlefield"):
        if card_name(card) != "Devoted Druid":
            continue
        raw = json.dumps(card, sort_keys=True).lower()
        if "artifact" in raw and ("creature" not in raw or "machine god's effigy" in raw):
            if available & OUTLETS:
                return "Machine God's Effigy (Devoted Druid) + deterministic outlet"
    return None


def protection_available(snapshot: dict[str, Any], kinnan_seat: int) -> list[str]:
    available = names_in(snapshot, kinnan_seat, "hand") | names_in(
        snapshot, kinnan_seat, "battlefield"
    )
    return sorted(available & (TRUE_COUNTERS | SELF_PROTECTION))


def visible_state_hash(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def legal_action_hash(actions: Iterable[dict[str, Any]]) -> str:
    payload = json.dumps(list(actions), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def next_step_target(snapshot: dict[str, Any]) -> dict[str, str] | None:
    """Return a protocol-valid next-phase fast-forward target.

    This is only used after the same pass-only priority state repeats.  Legal
    actions are still offered once before the pilot asks the pinned harness to
    advance, so normal interaction windows are preserved.
    """

    step = str(snapshot.get("step") or "")
    active = str(snapshot.get("activePlayerId") or "")
    if step not in TURN_STEPS or not active:
        return None
    index = TURN_STEPS.index(step)
    if index + 1 < len(TURN_STEPS):
        return {"playerId": active, "phase": TURN_STEPS[index + 1]}
    active_index = player_index(active)
    players = [
        player_index(item.get("id"))
        for item in (snapshot.get("players", []) or [])
        if not item.get("hasLost") and not item.get("lost")
    ]
    live = sorted(item for item in players if item is not None)
    if active_index is None or not live:
        return None
    later = [item for item in live if item > active_index]
    next_player = min(later) if later else min(live)
    return {"playerId": f"player-{next_player}", "phase": "untap"}


def recovered_pass_output(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build the documented safe-pass response for a repeated priority state."""

    if snapshot.get("stack"):
        return {"type": "pass", "exhaustStack": True}
    output: dict[str, Any] = {"type": "pass", "exhaustStack": False}
    target = next_step_target(snapshot)
    if target:
        output["until"] = target
    return output


def combo_action_score(line: str | None, name: str, action: dict[str, Any]) -> int:
    """Score only actions that advance an already recognized deterministic line.

    Forge's advertised action IDs remain the legality authority.  In
    particular, no mana-pool estimate is used: if an untap or outlet action is
    advertised, it is legal to select and complete its payment prompt.
    """

    if not line:
        return -1
    action_type = str(action.get("type") or "")
    description = str(action.get("description") or action.get("label") or "").lower()
    if action_type == "cast" and name in OUTLETS:
        return 10_000
    if action_type != "activateAbility":
        return -1
    if name == "Thrasios, Triton Hero":
        return 9_900
    if name == "Staff of Domination":
        if "draw a card" in description:
            return 9_950
        if "untap" in description and "staff" in description:
            return 9_925
        return 9_000
    if name == "Walking Ballista" and any(
        token in description for token in ("damage", "remove a +1/+1 counter")
    ):
        return 10_050
    if name == "Kinnan, Bonder Prodigy":
        return 9_700
    if name in MONOLITHS:
        if "untap" in description:
            return 9_600
        if action.get("isManaAbility") or "add" in description:
            return 9_500
    if name == "Forensic Gadgeteer" and "untap" in description:
        return 9_400
    return -1


def is_attempt_action(line: str | None, name: str, action: dict[str, Any] | None) -> bool:
    """Require an outlet or engine activation, not generic post-assembly activity."""

    if not line or not action:
        return False
    action_type = str(action.get("type") or "")
    if action_type == "cast" and name in OUTLETS:
        return True
    return action_type == "activateAbility" and name in {
        "Kinnan, Bonder Prodigy",
        "Thrasios, Triton Hero",
        "Staff of Domination",
    }


def _life_by_player(snapshot: dict[str, Any]) -> dict[str, int]:
    return {
        str(player.get("id")): int(player.get("life", 40))
        for player in snapshot.get("players", []) or []
    }


def choose_attackers(
    inp: dict[str, Any], snapshot: dict[str, Any], player: int, deck: str
) -> list[dict[str, str]]:
    """Attack with useful bodies while preserving Kinnan engine creatures."""

    cards = card_map(snapshot)
    life = _life_by_player(snapshot)
    assignments: list[dict[str, str]] = []
    for option in inp.get("attackers", []) or []:
        attacker_id = str(option.get("attackerId") or "")
        card = cards.get(attacker_id, {})
        name = card_name(card)
        if not attacker_id:
            continue
        if deck == "Kinnan" and name in ENGINE_CREATURES:
            continue
        valid = [
            str(target)
            for target in option.get("validTargetIds", []) or []
            if str(target) != f"player-{player}"
        ]
        if not valid:
            continue
        player_targets = [target for target in valid if target.startswith("player-")]
        target = min(player_targets or valid, key=lambda item: life.get(item, 10**9))
        assignments.append({"attackerId": attacker_id, "targetId": target})
    return assignments


def _integer_stat(card: dict[str, Any], key: str) -> int:
    value = card.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def choose_blockers(
    inp: dict[str, Any], snapshot: dict[str, Any], player: int, deck: str
) -> list[dict[str, str]]:
    """Satisfy mandatory blocks and take favorable blocks without donating engines."""

    cards = card_map(snapshot)
    available = set(str(item) for item in inp.get("availableBlockerIds", []) or [])
    assignments: list[dict[str, str]] = []
    player_state = next(
        (item for item in snapshot.get("players", []) or [] if item.get("id") == f"player-{player}"),
        {},
    )
    low_life = int(player_state.get("life", 40)) <= 8

    attackers = sorted(
        inp.get("attackers", []) or [],
        key=lambda item: (not bool(item.get("mustBeBlocked")), -_integer_stat(cards.get(str(item.get("attackerId")), {}), "power")),
    )
    for attacker in attackers:
        attacker_id = str(attacker.get("attackerId") or "")
        attacker_card = cards.get(attacker_id, {})
        attacker_power = _integer_stat(attacker_card, "power")
        candidates = [
            blocker_id
            for blocker_id in attacker.get("validBlockerIds", []) or []
            if str(blocker_id) in available
        ]
        safe: list[tuple[int, str]] = []
        emergency: list[tuple[int, str]] = []
        for raw_id in candidates:
            blocker_id = str(raw_id)
            blocker = cards.get(blocker_id, {})
            name = card_name(blocker)
            toughness = _integer_stat(blocker, "toughness")
            power = _integer_stat(blocker, "power")
            engine_penalty = 100 if deck == "Kinnan" and name in ENGINE_CREATURES else 0
            score = power + toughness - engine_penalty
            emergency.append((score, blocker_id))
            if toughness > attacker_power and engine_penalty == 0:
                safe.append((score, blocker_id))

        minimum = max(1, int(attacker.get("minBlockers", 1) or 1))
        required = minimum if attacker.get("mustBeBlocked") else 0
        pool = safe if len(safe) >= minimum else emergency if (required or low_life) else []
        # Menace-like restrictions make a one-blocker assignment illegal even
        # when blocking is optional.  Omit the block unless the advertised
        # minimum can be satisfied; otherwise Forge repeats chooseBlockers.
        take = max(required, minimum if len(pool) >= minimum and (safe or low_life) else 0)
        if len(pool) < take:
            take = 0
        for _, blocker_id in sorted(pool, reverse=True)[:take]:
            assignments.append({"blockerId": blocker_id, "attackerId": attacker_id})
            available.discard(blocker_id)
    return assignments


def choose_boolean(inp: dict[str, Any], deck: str, combo_ready: bool) -> bool:
    text = " ".join(
        [
            str((inp.get("presentation") or {}).get("title") or ""),
            str((inp.get("presentation") or {}).get("description") or ""),
            str(inp.get("confirmLabel") or ""),
        ]
    ).lower()
    # Optional riders are policy choices.  Required costs are not: once the
    # controller has selected the advertised spell/ability, declining a fetch
    # land's life payment (or Mana Confluence's) merely returns to the same
    # prompt and creates an infinite action/decision loop.
    if any(
        token in text
        for token in (
            "pay buyback",
            "kicker",
            "multikicker",
            "replicate",
            "additional optional cost",
            "unless you pay",
        )
    ):
        return combo_ready
    if any(
        token in text
        for token in (
            "pay 1 life",
            "pay 2 life",
            "pay 3 life",
            "pay 4 life",
            "sacrifice ",
            "discard ",
            "exile ",
        )
    ):
        return True
    if any(token in text for token in ("search", "draw", "untap", "copy", "counter", "use this ability")):
        return True
    if any(token in text for token in ("sacrifice", "discard", "lose life")):
        return combo_ready
    return False


def choose_payment_action(inp: dict[str, Any]) -> tuple[str, str | None]:
    """Choose a color-correct, engine-advertised mana action.

    Returns ``("confirm", None)``, ``("act", action_id)``, or
    ``("cancel", None)``.  The engine still owns legality and the remaining
    cost; this function only prevents an arbitrary first-color choice such as
    asking Mana Confluence for white while paying ``{B}``.
    """

    if inp.get("canConfirmFromPool"):
        return "confirm", None

    symbols = re.findall(r"\{([^}]+)\}", str(inp.get("manaCost") or "").upper())
    required_colors = {symbol for symbol in symbols if symbol in {"W", "U", "B", "R", "G", "C"}}

    def safe_unannotated_mana(action: dict[str, Any]) -> bool:
        if action.get("type") != "activateManaAbility" or not action.get("isManaAbility"):
            return False
        text = " ".join(
            str(action.get(key) or "")
            for key in ("description", "label", "cardName")
        ).lower()
        return any(
            token in text
            for token in (
                "add one mana",
                "command tower",
                "city of brass",
                "mana confluence",
                "colors among legendary",
                "exiled card's colors",
            )
        )

    productive = [
        action
        for action in (inp.get("actions", []) or [])
        if (
            action.get("type") in {"useResource", "payLife"}
            or (
                action.get("type") == "activateManaAbility"
                and (bool(action.get("producedMana")) or safe_unannotated_mana(action))
            )
        )
        # A filter such as Energy Refractor's {2}: add one mana cannot make
        # progress toward the outer payment.  Selecting it makes Forge offer
        # the same action forever once ordinary sources are exhausted.
        and not re.search(r"\{(?:\d+|[WUBRGCX])\}", str(action.get("cost") or "").upper())
    ]
    if not productive:
        return "cancel", None

    def score(action: dict[str, Any]) -> tuple[int, int, str]:
        produced = {
            str(item.get("color") or "").upper()
            for item in (action.get("producedMana", []) or [])
        }
        text = " ".join(
            str(action.get(key) or "")
            for key in ("description", "label", "cardName")
        ).lower()
        flexible = not produced and any(
            token in text
            for token in ("any color", "command tower", "city of brass", "mana confluence")
        )
        exact = len(required_colors & produced) + (1 if required_colors and flexible else 0)
        colored = len(produced & {"W", "U", "B", "R", "G"})
        kind = 2 if action.get("type") == "activateManaAbility" else 1
        return exact * 100 + colored * 10 + (1 if "C" in produced else 0), kind, str(action.get("id") or "")

    chosen = max(productive, key=score)
    return "act", str(chosen.get("id"))


def required_payment_colors(inp: dict[str, Any]) -> list[str]:
    """Return colored requirements in deterministic protocol-choice order."""

    symbols = re.findall(r"\{([^}]+)\}", str(inp.get("manaCost") or "").upper())
    return [symbol for symbol in symbols if symbol in {"W", "U", "B", "R", "G", "C"}]


def choose_payment_color(inp: dict[str, Any], preferred: list[str]) -> str:
    available = [
        str(item).upper()
        for item in (inp.get("availableColors") or inp.get("colors") or [])
    ]
    for color in preferred:
        if color in available:
            return color
    return available[0] if available else (preferred[0] if preferred else "U")


def _option_score(option: dict[str, Any], deck: str) -> int:
    label = str(option.get("label") or option.get("description") or "").lower()
    score = 0
    for token, value in (
        ("win", 100),
        ("search", 40),
        ("draw", 35),
        ("untap", 30),
        ("counter", 28),
        ("destroy", 20),
        ("return", 14),
        ("create", 10),
        ("discard", -18),
        ("lose life", -20),
        ("sacrifice", -22),
    ):
        if token in label:
            score += value
    if deck == "Kinnan" and any(token in label for token in ("artifact", "mana", "creature")):
        score += 12
    return score


def choose_selection(inp: dict[str, Any], deck: str) -> list[int]:
    """Return the highest-scoring protocol-valid modal selection."""

    options = inp.get("options", []) or []
    minimum = int(inp.get("minTotal", 0) or 0)
    maximum = int(inp.get("maxTotal", minimum) or minimum)
    if not options:
        return []

    per_option_limits = [
        max(1, maximum // max(1, int(option.get("weight", 1) or 1)))
        if option.get("canRepeat")
        else 1
        for option in options
    ]
    best: tuple[int, list[int]] | None = None
    for counts in product(*(range(limit + 1) for limit in per_option_limits)):
        weight = sum(
            count * max(1, int(options[index].get("weight", 1) or 1))
            for index, count in enumerate(counts)
        )
        if not minimum <= weight <= maximum:
            continue
        chosen = [index for index, count in enumerate(counts) for _ in range(count)]
        score = sum(_option_score(options[index], deck) for index in chosen)
        candidate = (score, chosen)
        if best is None or candidate > best:
            best = candidate
    return best[1] if best else []


def primary_failure(result: dict[str, Any]) -> str | None:
    if result.get("status") in {"crash", "unsupported_prompt"}:
        return "ENGINE_ERROR"
    if result.get("status") == "protocol_stall":
        return "PROTOCOL_STALL"
    if result.get("status") in {
        "idle_timeout",
        "stale_prompt_timeout",
        "wall_timeout",
        "prompt_cap",
        "round_cap",
    }:
        return "TIMEOUT"
    if result.get("kinnanWon"):
        return None
    if result.get("firstAttemptTurn") is not None:
        return "UNRESOLVED_ATTEMPT"
    if result.get("firstAssemblyTurn") is not None:
        return "PILOT_ERROR"
    return "NONDETERMINISTIC_ONLY"
