#!/usr/bin/env python3
"""Build complete, explicit per-game/per-card telemetry for a registered 99."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA = "kinnan-full99-card-telemetry-v2"
ACTION_KINDS = {"actionChosen"}


def deck_cards(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    start = lines.index("[Main]") + 1
    cards = [line.split(" ", 1)[1].strip() for line in lines[start:] if line.strip()]
    if len(cards) != 99 or len(set(cards)) != 99:
        raise ValueError(f"registered deck must contain exactly 99 distinct cards: {path}")
    return cards


def _turn(event: dict[str, Any]) -> int | None:
    value = event.get("round")
    return int(value) if isinstance(value, int) else None


def _first_turn(events: list[dict[str, Any]], kinds: set[str]) -> int | None:
    values = [_turn(e) for e in events if e.get("kind") in kinds]
    values = [v for v in values if v is not None]
    return min(values) if values else None


def attach(compact: dict[str, Any], result: dict[str, Any], deck_path: Path) -> dict[str, Any]:
    cards = deck_cards(deck_path)
    telemetry = result.get("cardTelemetry") or {}
    events = list(telemetry.get("events") or [])
    opening = set(telemetry.get("openingHand") or [])
    kept = set(telemetry.get("keptHand") or [])
    rejected = {
        card
        for hand in telemetry.get("mulliganHands") or []
        if not hand.get("keep")
        for card in hand.get("cards") or []
    }
    put_back = set(telemetry.get("putBackCards") or [])
    combo_text = json.dumps(result.get("comboLine") or "", sort_keys=True)
    win = bool(result.get("kinnanWon"))
    strict_protected = bool(result.get("strictProtectedT4"))
    rows: list[dict[str, Any]] = []

    for card in cards:
        card_events = [e for e in events if e.get("card") == card or e.get("targetCard") == card]
        actions = [e for e in card_events if e.get("kind") in ACTION_KINDS]
        zone_changes = [e for e in card_events if e.get("kind") == "zoneTransition"]
        zones = sorted({str(e.get("toZone")) for e in zone_changes if e.get("toZone")})
        drawn = [e for e in card_events if e.get("kind") == "draw"]
        casts = [e for e in actions if str(e.get("actionType") or "").lower() == "cast"]
        plays = [e for e in actions if str(e.get("actionType") or "").lower() in {"play", "playland", "land"}]
        activations = [e for e in actions if str(e.get("actionType") or "").lower() in {"activate", "ability", "mana"}]
        targeted = [e for e in card_events if e.get("kind") == "targeted"]
        protection = any(card in (e.get("protectionInHand") or []) or card in (e.get("protectionOnBattlefield") or []) for e in events)
        protection = protection or any(bool(e.get("hasProtection")) for e in actions)
        combo = card.lower() in combo_text.lower()
        involved = bool(card_events or card in opening or card in kept or card in rejected or card in put_back)
        essential = bool(combo or (strict_protected and protection and actions))
        rows.append({
            "schemaVersion": SCHEMA,
            "deckHash": compact.get("variantDeckSha256") or result.get("variantDeckSha256"),
            "variant": compact.get("variant") or result.get("variant"),
            "card": card,
            "seed": compact.get("seed") or result.get("seed"),
            "seat": compact.get("kinnanSeat") or result.get("kinnanSeat"),
            "pod": compact.get("podProfile"),
            "registeredPresent": True,
            "openingHand": card in opening,
            "kept": card in kept,
            "mulliganed": card in rejected or card in put_back,
            "firstSeenTurn": _first_turn(card_events, {"draw", "zoneTransition", "actionChosen", "targeted"}),
            "firstDrawnTurn": _first_turn(drawn, {"draw"}),
            "zonesSeen": zones,
            "zoneChanges": zone_changes,
            "tutored": any(e.get("kind") == "tutored" for e in card_events),
            "revealed": any(e.get("kind") == "revealed" for e in card_events),
            "cast": bool(casts),
            "played": bool(plays),
            "manaProduced": 0,
            "manaSpent": 0,
            "activated": bool(activations),
            "used": bool(actions),
            "comboParticipation": combo,
            "protectionParticipation": protection,
            "interactionParticipation": bool(targeted),
            "naturalWinPresence": bool(win and involved),
            "assemblyPresence": bool((result.get("firstAssemblyTurn") or 99) <= 4 and involved),
            "attemptPresence": bool((result.get("firstAttemptTurn") or 99) <= 4 and involved),
            "protectedAttemptPresence": bool(strict_protected and involved),
            "packageExecution": bool(actions and (combo or protection)),
            "outcomeAttribution": "essential" if essential else ("involved" if involved else "present"),
        })

    compact["cardTelemetrySchemaVersion"] = SCHEMA
    compact["cardTelemetryRows"] = rows
    compact["cardTelemetryCoverage"] = {
        "expectedRows": 99,
        "actualRows": len(rows),
        "distinctCards": len({r["card"] for r in rows}),
        "missingCards": sorted(set(cards) - {r["card"] for r in rows}),
        "duplicates": sorted(card for card in cards if sum(r["card"] == card for r in rows) > 1),
    }
    compact["rawActionTrace"] = events
    return compact
