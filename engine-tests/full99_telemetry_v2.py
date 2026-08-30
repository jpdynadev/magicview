#!/usr/bin/env python3
"""Build complete, explicit per-game/per-card telemetry for a registered 99."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA = "kinnan-full99-card-telemetry-v2"
ACTION_KINDS = {"actionChosen"}


def _prompt_cards(event: dict[str, Any]) -> list[dict[str, Any]]:
    return list(((event.get("inputSummary") or {}).get("cards") or []))


def _prompt_card_name(card: dict[str, Any]) -> str:
    return str(((card.get("identity") or {}).get("name") or card.get("name") or ""))


def _chosen_prompt_cards(event: dict[str, Any]) -> list[dict[str, Any]]:
    chosen = {
        str(value)
        for value in ((event.get("chosenOutput") or {}).get("chosenCardIds") or [])
    }
    return [card for card in _prompt_cards(event) if str(card.get("id") or "") in chosen]


def _source_title(event: dict[str, Any]) -> str:
    presentation = (event.get("inputSummary") or {}).get("presentation") or {}
    return str(presentation.get("title") or "")


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
    # Forge exposes library looks/search choices as structured prompt payloads.
    # Preserve the distinction between cards shown by a reveal prompt and cards
    # actually selected by a search effect; never infer either from deck membership.
    source_text: dict[str, str] = {}
    for event in events:
        if event.get("kind") != "actionChosen":
            continue
        raw_card = event.get("rawCard") or {}
        name = str(((raw_card.get("identity") or {}).get("name") or event.get("card") or ""))
        text = str(raw_card.get("text") or "")
        if name and text:
            source_text[name] = text
    reveal_events_by_card: dict[str, list[dict[str, Any]]] = {}
    tutor_events_by_card: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("kind") != "promptDecision":
            continue
        ptype = str(event.get("promptType") or "")
        if ptype == "revealCards":
            for prompt_card in _prompt_cards(event):
                name = _prompt_card_name(prompt_card)
                if name:
                    reveal_events_by_card.setdefault(name, []).append(event)
        elif ptype == "chooseCards":
            source = _source_title(event)
            rules = source_text.get(source, "")
            if "search your library" not in rules.lower():
                continue
            for prompt_card in _chosen_prompt_cards(event):
                name = _prompt_card_name(prompt_card)
                if name:
                    tutor_events_by_card.setdefault(name, []).append(event)
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
        semantic_events = reveal_events_by_card.get(card, []) + tutor_events_by_card.get(card, [])
        card_events = [e for e in events if e.get("card") == card or e.get("targetCard") == card] + semantic_events
        actions = [e for e in card_events if e.get("kind") in ACTION_KINDS]
        zone_changes = [e for e in card_events if e.get("kind") == "zoneTransition"]
        zones = sorted({str(e.get("toZone")) for e in zone_changes if e.get("toZone")})
        drawn = [e for e in card_events if e.get("kind") == "draw"]
        casts = [
            e for e in actions
            if str(e.get("actionType") or "").lower() == "cast"
            and not str(e.get("description") or "").lower().startswith("play ")
        ]
        plays = [
            e for e in actions
            if str(e.get("actionType") or "").lower() in {"play", "playland", "land"}
            or str(e.get("description") or "").lower().startswith("play ")
        ]
        activations = [e for e in actions if str(e.get("actionType") or "").lower() in {"activate", "ability", "mana"}]
        targeted = [e for e in card_events if e.get("kind") == "targeted"]
        protection = any(card in (e.get("protectionInHand") or []) or card in (e.get("protectionOnBattlefield") or []) for e in events)
        protection = protection or any(bool(e.get("hasProtection")) for e in actions)
        combo = card.lower() in combo_text.lower()
        involved = bool(card_events or card in opening or card in kept or card in rejected or card in put_back)
        essential = bool(combo or (strict_protected and protection and actions))
        rows.append({
            "schemaVersion": SCHEMA,
            "engineId": compact.get("engineId") or result.get("engineId"),
            "cacheKey": compact.get("cacheKey"),
            "pilotVersion": compact.get("pilotVersion") or result.get("pilotVersion"),
            "deckHash": compact.get("variantDeckSha256") or result.get("variantDeckSha256"),
            "variant": compact.get("variant") or result.get("variant"),
            "card": card,
            "seed": compact.get("seed") or result.get("seed"),
            "seat": compact.get("kinnanSeat") or result.get("kinnanSeat"),
            "pod": compact.get("podProfile"),
            "gameStatus": compact.get("status") or result.get("status"),
            "registeredPresent": True,
            "openingHand": card in opening,
            "kept": card in kept,
            "mulliganed": card in rejected or card in put_back,
            "firstSeenTurn": _first_turn(card_events, {"draw", "zoneTransition", "actionChosen", "targeted"}),
            "firstDrawnTurn": _first_turn(drawn, {"draw"}),
            "zonesSeen": zones,
            "zoneChanges": zone_changes,
            "tutored": bool(tutor_events_by_card.get(card)),
            "tutorEvents": tutor_events_by_card.get(card, []),
            "revealed": bool(reveal_events_by_card.get(card)),
            "revealEvents": reveal_events_by_card.get(card, []),
            "cast": bool(casts),
            "played": bool(plays),
            "manaProduced": 0,
            "manaSpent": 0,
            "manaAttributionComplete": False,
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
