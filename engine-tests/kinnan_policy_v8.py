"""Pure policy and measurement helpers for the Forge/Manabrew v8 pilot.

This module deliberately has no dependency on Forge or the legacy pilot modules so
that the protocol-critical decisions can be unit tested before a JVM game starts.
"""

from __future__ import annotations

import hashlib
import json
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

    if {"Grim Monolith", "Power Artifact"} <= battlefield:
        if available & OUTLETS:
            return "Grim Monolith + Power Artifact + deterministic outlet"

    if {"Kinnan, Bonder Prodigy", "Grim Monolith", "Forensic Gadgeteer"} <= battlefield:
        if available & OUTLETS:
            return "Kinnan + Grim + Forensic Gadgeteer + deterministic outlet"

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

        required = int(attacker.get("minBlockers", 1) or 1) if attacker.get("mustBeBlocked") else 0
        pool = safe if safe else emergency if (required or low_life) else []
        take = max(required, 1 if (pool and (safe or low_life)) else 0)
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
    if any(token in text for token in ("pay buyback", "additional cost", "unless you pay")):
        return combo_ready
    if any(token in text for token in ("search", "draw", "untap", "copy", "counter", "use this ability")):
        return True
    if any(token in text for token in ("sacrifice", "discard", "lose life")):
        return combo_ready
    return False


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
    if result.get("status") in {"idle_timeout", "stale_prompt_timeout", "prompt_cap", "round_cap"}:
        return "TIMEOUT"
    if result.get("kinnanWon"):
        return None
    if result.get("firstAttemptTurn") is not None:
        return "COUNTERWAR"
    if result.get("firstAssemblyTurn") is not None:
        return "PROTECTION"
    return "NONDETERMINISTIC_ONLY"
