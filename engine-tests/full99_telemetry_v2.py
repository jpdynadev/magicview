#!/usr/bin/env python3
"""Build complete, explicit per-game/per-card telemetry for a registered 99."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "kinnan-full99-card-telemetry-v2"
ACTION_KINDS = {"actionChosen"}
MANA_COLORS = {
    "White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G",
    "Colorless": "C", "W": "W", "U": "U", "B": "B", "R": "R", "G": "G", "C": "C",
}


def _mana_value(cost: str) -> int | None:
    """Return the exact value of a concrete Manabrew cost, or None if ambiguous."""
    symbols = re.findall(r"\{([^}]+)\}", str(cost or ""))
    if not symbols and cost:
        return None
    total = 0
    for symbol in symbols:
        if symbol.isdigit():
            total += int(symbol)
        elif symbol in {"W", "U", "B", "R", "G", "C", "S"}:
            total += 1
        else:
            # X, hybrid, phyrexian and other alternate/resource costs require
            # their own observed payment record.  Never estimate them here.
            return None
    return total


def _payment_attribution(events: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    """Derive exact target spend and source production from observed payment sessions."""
    sessions: dict[str, list[dict[str, Any]]] = {}
    ordered = sorted(events, key=lambda event: int(event.get("seq") or 0))
    for event in ordered:
        if event.get("kind") == "manaPaymentDecision":
            sessions.setdefault(str(event.get("paymentSession")), []).append(event)

    # Flexible mana abilities (for example Arcane Signet) advertise the source
    # action first and then ask chooseColor.  Pair only the immediately following
    # observed color decision before the next payment decision.
    color_after_seq: dict[int, list[dict[str, Any]]] = {}
    for index, event in enumerate(ordered):
        if event.get("kind") != "manaPaymentDecision" or event.get("decisionType") != "act":
            continue
        colors: list[dict[str, Any]] = []
        for following in ordered[index + 1:]:
            if following.get("kind") == "manaPaymentDecision":
                break
            if following.get("kind") == "promptDecision" and following.get("promptType") == "chooseColor":
                chosen = (following.get("chosenOutput") or {}).get("chosenColors") or {}
                for color, amount in chosen.items():
                    normalized = MANA_COLORS.get(str(color))
                    if normalized and isinstance(amount, int) and amount > 0:
                        colors.append({"color": normalized, "amount": amount})
        color_after_seq[int(event.get("seq") or 0)] = colors

    targets: dict[str, dict[str, Any]] = {}
    produced_by_card: dict[str, int] = {}
    payment_traces: list[dict[str, Any]] = []
    for session_id, decisions in sessions.items():
        first = decisions[0]
        final = decisions[-1]
        target = str(first.get("card") or "")
        target_id = str(first.get("cardId") or "")
        cost = str(first.get("initialRemainingCost") or "")
        successful = final.get("decisionType") == "pay" and not final.get("canceled")
        exact_cost = _mana_value(cost)
        source_events = []
        sources_complete = True
        for decision in decisions:
            if decision.get("decisionType") != "act":
                continue
            action = decision.get("selectedAction") or {}
            source = str(decision.get("sourceCard") or action.get("description") or "")
            source_snapshot = decision.get("sourceCardSnapshot") or {}
            mana = list(decision.get("producedMana") or action.get("producedMana") or [])
            if not mana:
                mana = color_after_seq.get(int(decision.get("seq") or 0), [])
            valid_mana = bool(mana) and all(
                MANA_COLORS.get(str(item.get("color"))) and isinstance(item.get("amount"), int)
                and item.get("amount") > 0 for item in mana
            )
            battlefield = set(decision.get("battlefieldBefore") or [])
            type_line = str(source_snapshot.get("typeLine") or source_snapshot.get("type") or "")
            taps_source = "{T}" in str(action.get("cost") or "")
            kinnan_bonus = "Kinnan, Bonder Prodigy" in battlefield and taps_source and "Land" not in type_line
            if kinnan_bonus:
                distinct = {MANA_COLORS.get(str(item.get("color"))) for item in mana}
                distinct.discard(None)
                if valid_mana and len(distinct) == 1:
                    mana = list(mana) + [{"color": next(iter(distinct)), "amount": 1, "source": "Kinnan bonus"}]
                else:
                    # The effective bonus type is not exact unless the trace
                    # contains one unambiguous produced type.
                    valid_mana = False
            sources_complete = sources_complete and bool(source) and valid_mana
            amount = sum(int(item.get("amount") or 0) for item in mana) if valid_mana else 0
            if source and amount:
                produced_by_card[source] = produced_by_card.get(source, 0) + amount
            source_events.append({
                "sourceCard": source,
                "sourceCardId": decision.get("sourceCardId") or action.get("cardId"),
                "sourceCardSnapshot": source_snapshot,
                "action": action,
                "producedMana": mana,
                "amount": amount,
                "exact": bool(source) and valid_mana,
            })
        complete = bool(successful and target and exact_cost is not None and sources_complete)
        trace = {
            "paymentSession": session_id,
            "targetCard": target,
            "targetCardId": target_id,
            "initialRemainingCost": cost,
            "manaSpent": exact_cost if successful and exact_cost is not None else 0,
            "successful": successful,
            "complete": complete,
            "sources": source_events,
        }
        payment_traces.append(trace)
        if target:
            entry = targets.setdefault(target, {"manaSpent": 0, "complete": True, "sessions": []})
            entry["sessions"].append(trace)
            if successful:
                entry["manaSpent"] += trace["manaSpent"]
                entry["complete"] = bool(entry["complete"] and complete)
    return targets, produced_by_card, payment_traces


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
    looked_at_events_by_card: dict[str, list[dict[str, Any]]] = {}
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
                    looked_at_events_by_card.setdefault(name, []).append(event)
        elif ptype == "chooseCards":
            source = _source_title(event)
            rules = source_text.get(source, "")
            if "search your library" not in rules.lower():
                continue
            for prompt_card in _chosen_prompt_cards(event):
                name = _prompt_card_name(prompt_card)
                if name:
                    tutor_events_by_card.setdefault(name, []).append(event)
                    if "reveal" in rules.lower():
                        reveal_events_by_card.setdefault(name, []).append(event)
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
    payment_targets, produced_by_card, payment_traces = _payment_attribution(events)
    rows: list[dict[str, Any]] = []

    for card in cards:
        semantic_events = looked_at_events_by_card.get(card, []) + reveal_events_by_card.get(card, []) + tutor_events_by_card.get(card, [])
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
            "lookedAt": bool(looked_at_events_by_card.get(card)),
            "lookedAtEvents": looked_at_events_by_card.get(card, []),
            "cast": bool(casts),
            "played": bool(plays),
            "manaProduced": produced_by_card.get(card, 0),
            "manaSpent": (payment_targets.get(card) or {}).get("manaSpent", 0),
            "manaPaymentEvents": (payment_targets.get(card) or {}).get("sessions", []),
            "manaAttributionComplete": (payment_targets.get(card) or {}).get("complete", True),
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
    compact["manaPaymentTrace"] = payment_traces
    compact["manaPaymentAttributionComplete"] = all(
        not trace["successful"] or trace["complete"] for trace in payment_traces
    )
    return compact
