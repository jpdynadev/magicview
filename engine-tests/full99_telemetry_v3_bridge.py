#!/usr/bin/env python3
"""Bridge live full-99 v2 artifacts into semantic v3 rows.

The v2 extractor remains the source adapter for current Forge/Manabrew traces. This
module assigns stable registered-card identities, preserves every explicit zero, and
fails closed unless both v2 and v3 independently cover the exact registered 99.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from kinnan_semantics_v9 import (
    FULL99_SCHEMA_VERSION,
    SemanticError,
    build_full99_rows,
    stable_semantic_hash,
    validate_full99_coverage,
)


def _deck_cards(path: Path) -> list[str]:
    section = ""
    cards: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.lower()
            continue
        if section != "[main]":
            continue
        count, name = line.split(" ", 1)
        cards.extend([name.strip()] * int(count))
    if len(cards) != 99 or len(set(cards)) != 99:
        raise SemanticError(f"registered deck must contain exactly 99 unique main cards: {path}")
    return cards


def _registered_id(deck_hash: str, card_name: str) -> str:
    return hashlib.sha256(f"{deck_hash}\0{card_name}".encode()).hexdigest()


def _as_mana_mapping(value: Any) -> dict[str, int]:
    if isinstance(value, Mapping):
        return {str(key): int(amount) for key, amount in value.items()}
    amount = int(value or 0)
    return {"total": amount} if amount else {}


def attach_v3(compact: dict[str, Any], result: dict[str, Any], deck_path: Path) -> dict[str, Any]:
    deck_hash = str(compact.get("variantDeckSha256") or result.get("variantDeckSha256") or "")
    if not deck_hash:
        raise SemanticError("v3 telemetry requires an exact deck hash")
    cards = _deck_cards(deck_path)
    v2_rows = list(compact.get("cardTelemetryRows") or [])
    by_name = {str(row.get("card") or ""): row for row in v2_rows}
    if len(v2_rows) != 99 or len(by_name) != 99 or set(by_name) != set(cards):
        raise SemanticError("v3 bridge requires exact v2 99-card coverage; legacy/partial rows remain NR")

    registered = [
        {
            "registeredCardId": _registered_id(deck_hash, name),
            "cardName": name,
        }
        for name in cards
    ]
    observed: dict[str, dict[str, Any]] = {}
    for card in registered:
        cid = card["registeredCardId"]
        row = by_name[card["cardName"]]
        seen = bool(
            row.get("openingHand")
            or row.get("kept")
            or row.get("mulliganed")
            or row.get("firstSeenTurn") is not None
            or row.get("firstDrawnTurn") is not None
            or row.get("zoneChanges")
            or row.get("tutored")
            or row.get("revealed")
            or row.get("cast")
            or row.get("played")
            or row.get("activated")
            or row.get("used")
        )
        attribution = str(row.get("outcomeAttribution") or "present")
        observed[cid] = {
            "seen": seen,
            "openingHand": bool(row.get("openingHand")),
            "kept": bool(row.get("kept")),
            "mulliganed": bool(row.get("mulliganed")),
            "firstSeenTurn": row.get("firstSeenTurn"),
            "firstDrawnTurn": row.get("firstDrawnTurn"),
            "zoneChanges": list(row.get("zoneChanges") or []),
            "tutored": bool(row.get("tutored")),
            "revealed": bool(row.get("revealed")),
            "cast": bool(row.get("cast")),
            "played": bool(row.get("played")),
            "manaProduced": _as_mana_mapping(row.get("manaProduced")),
            "manaSpent": int(row.get("manaSpent") or 0),
            "activated": bool(row.get("activated")),
            "used": bool(row.get("used")),
            "comboParticipation": bool(row.get("comboParticipation")),
            "protectionParticipation": bool(row.get("protectionParticipation")),
            "interactionParticipation": bool(row.get("interactionParticipation")),
            "attemptPresent": bool(row.get("attemptPresence")),
            "protectedAttemptPresent": bool(row.get("protectedAttemptPresence")),
            "naturalWinPresence": bool(row.get("naturalWinPresence")),
            "packageExecution": bool(row.get("packageExecution")),
            "involved": attribution in {"involved", "essential"},
            "essential": attribution == "essential",
        }

    game_key = {
        "engineId": compact.get("engineId") or result.get("engineId"),
        "deckHash": deck_hash,
        "seed": compact.get("seed") or result.get("seed"),
        "seat": compact.get("kinnanSeat") if compact.get("kinnanSeat") is not None else result.get("kinnanSeat"),
        "pod": compact.get("podProfile"),
        "horizon": compact.get("horizon") or result.get("maxRound") or 4,
    }
    game_id = stable_semantic_hash(game_key)
    rows = build_full99_rows(
        game_id=game_id,
        deck_hash=deck_hash,
        registered_cards=registered,
        observed_by_card_id=observed,
    )
    ids = [card["registeredCardId"] for card in registered]
    coverage = validate_full99_coverage(
        rows,
        valid_game_ids=[game_id],
        registered_card_ids_by_game={game_id: ids},
    )
    raw = list(compact.get("rawActionTrace") or [])
    compact["cardTelemetryV3SchemaVersion"] = FULL99_SCHEMA_VERSION
    compact["cardTelemetryV3Rows"] = rows
    compact["cardTelemetryV3Coverage"] = coverage
    compact["registeredCardIdentityMap"] = {
        card["registeredCardId"]: card["cardName"] for card in registered
    }
    compact["rawActionTraceHash"] = stable_semantic_hash(raw)
    compact["rawActionTraceEventCount"] = len(raw)
    compact["telemetryV3Complete"] = bool(coverage["valid"])
    if not compact["telemetryV3Complete"]:
        raise SemanticError(f"v3 coverage failed: {coverage}")
    return compact

