#!/usr/bin/env python3
"""Read-only card-level telemetry for Kinnan simulation games.

This module observes the same Forge snapshots/prompts already consumed by the
pilot.  It never creates an action and never changes a score.  It records
mulligan hands, draw/zone transitions, chosen card actions, hand context,
protection availability, and target interactions so downstream analysis can
measure card performance conditionally rather than treating deck slots as
binary exposure.
"""
from __future__ import annotations

import copy
import json
from typing import Any

PROTECTION_CARDS = {
    "An Offer You Can't Refuse", "Dispel", "Fierce Guardianship",
    "Flusterstorm", "Force of Negation", "Force of Will", "Mental Misstep",
    "Mindbreak Trap", "Misdirection", "Pact of Negation", "Swan Song",
    "Veil of Summer", "Defense Grid", "Commandeer", "Disrupting Shoal",
    "Strix Serenade", "Consign to Memory",
}

PREGAME_STEPS = {"", "pregame", "mulligan", "opening_hand", "openinghand"}


def install(runner: Any) -> None:
    """Install telemetry wrappers once on the composed architecture runner."""
    if getattr(runner, "_CARD_TELEMETRY_V1_INSTALLED", False):
        return
    runner._CARD_TELEMETRY_V1_INSTALLED = True
    state: dict[str, Any] = {"ctx": None}
    base = runner.base

    def _name(card: dict[str, Any] | None) -> str:
        try:
            return base.card_name(card or {}) or ""
        except Exception:
            return ""

    def _seat_from_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int:
        try:
            return int(args[4] if len(args) > 4 else kwargs.get("kinnan_seat", 0))
        except Exception:
            return 0

    def _clock(snapshot: dict[str, Any]) -> dict[str, Any]:
        round_value = snapshot.get("round")
        if round_value is None:
            round_value = snapshot.get("turnNumber", snapshot.get("turn"))
        try:
            round_value = int(round_value) if round_value is not None else None
        except Exception:
            pass
        return {
            "round": round_value,
            "activePlayerId": snapshot.get("activePlayerId"),
            "step": snapshot.get("step") or snapshot.get("phase"),
        }

    def _mana_pool(snapshot: dict[str, Any], seat: int) -> dict[str, int]:
        wanted = f"player-{seat}"
        for p in snapshot.get("players", []) or []:
            if str(p.get("id") or "") == wanted:
                out = {}
                for k, v in (p.get("manaPool") or {}).items():
                    try:
                        out[str(k)] = int(v or 0)
                    except Exception:
                        continue
                return out
        return {}

    def _zone(snapshot: dict[str, Any], seat: int, zone: str) -> list[dict[str, Any]]:
        try:
            return list(base.zone_cards(snapshot, seat, zone) or [])
        except Exception:
            return []

    def _named_zone(snapshot: dict[str, Any], seat: int, zone: str) -> list[dict[str, str]]:
        out = []
        for card in _zone(snapshot, seat, zone):
            name = _name(card)
            cid = str(card.get("id") or "")
            if name:
                out.append({"id": cid, "name": name})
        return out

    def _hand_names(snapshot: dict[str, Any], seat: int) -> list[str]:
        return [x["name"] for x in _named_zone(snapshot, seat, "hand")]

    def _battlefield_names(snapshot: dict[str, Any], seat: int) -> list[str]:
        return [x["name"] for x in _named_zone(snapshot, seat, "battlefield")]

    def _game_started(snapshot: dict[str, Any]) -> bool:
        clock = _clock(snapshot)
        rv = clock.get("round")
        if isinstance(rv, int) and rv >= 1:
            return True
        step = str(clock.get("step") or "").lower()
        return step not in PREGAME_STEPS and bool(step)

    def _event(kind: str, **payload: Any) -> None:
        ctx = state.get("ctx")
        if not ctx:
            return
        ctx["seq"] += 1
        row = {"seq": ctx["seq"], "kind": kind}
        row.update(payload)
        ctx["events"].append(row)

    def _protection_context(snapshot: dict[str, Any], seat: int, played_card: str = "") -> tuple[list[str], list[str]]:
        hand = [x for x in _hand_names(snapshot, seat) if x != played_card]
        battlefield = _battlefield_names(snapshot, seat)
        return (
            sorted({x for x in hand if x in PROTECTION_CARDS}),
            sorted({x for x in battlefield if x in PROTECTION_CARDS}),
        )

    def _snapshot_zones(snapshot: dict[str, Any], seat: int) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        for zone in ("hand", "battlefield", "graveyard", "exile", "command"):
            for row in _named_zone(snapshot, seat, zone):
                if row["id"]:
                    card_obj = next((x for x in _zone(snapshot, seat, zone) if str(x.get("id") or "") == row["id"]), {})
                    result[row["id"]] = {
                        "name": row["name"], "zone": zone,
                        "tapped": bool(card_obj.get("tapped") or card_obj.get("isTapped")),
                    }
        return result

    def _observe_snapshot(snapshot: dict[str, Any]) -> None:
        ctx = state.get("ctx")
        if not ctx:
            return
        seat = int(ctx["seat"])
        current = _snapshot_zones(snapshot, seat)
        previous = ctx.get("zones") or {}
        clock = _clock(snapshot)

        if ctx.get("firstVisibleHand") is None:
            hand = _hand_names(snapshot, seat)
            if hand:
                ctx["firstVisibleHand"] = list(hand)
                _event("firstVisibleHand", cards=list(hand), **clock)

        if previous:
            for cid, now in current.items():
                before = previous.get(cid)
                if not before:
                    if now["zone"] == "hand" and _game_started(snapshot):
                        hand = _hand_names(snapshot, seat)
                        _event("draw", card=now["name"], cardId=cid, handAfter=hand, **clock)
                    continue
                if before["zone"] != now["zone"]:
                    _event(
                        "zoneTransition", card=now["name"], cardId=cid,
                        fromZone=before["zone"], toZone=now["zone"],
                        lastOpponentAction=copy.deepcopy(ctx.get("lastOpponentAction")),
                        **clock,
                    )
                if not before.get("tapped") and now.get("tapped"):
                    _event("tapped", card=now["name"], cardId=cid, zone=now["zone"], **clock)
                elif before.get("tapped") and not now.get("tapped"):
                    _event("untapped", card=now["name"], cardId=cid, zone=now["zone"], **clock)
        ctx["zones"] = current

    original_keep = base.keep_hand
    def telemetry_keep_hand(deck: str, hand: list[dict[str, Any]], mulligan_count: int) -> bool:
        decision = original_keep(deck, hand, mulligan_count)
        ctx = state.get("ctx")
        if ctx and deck == "Kinnan":
            cards = [_name(c) for c in hand if _name(c)]
            row = {"mulliganCount": int(mulligan_count), "cards": cards, "keep": bool(decision)}
            ctx["mulliganHands"].append(row)
            _event("mulliganDecision", **row)
            if decision:
                ctx["keptHand"] = list(cards)
        return decision
    base.keep_hand = telemetry_keep_hand

    original_response = base.response_for

    def _chosen_ids(value: Any) -> set[str]:
        out: set[str] = set()
        if isinstance(value, dict):
            for k, v in value.items():
                if k in {"cardId", "targetId", "id"} and isinstance(v, (str, int)):
                    out.add(str(v))
                elif k in {"cardIds", "targetIds", "chosenIds"} and isinstance(v, list):
                    out.update(str(x) for x in v if isinstance(x, (str, int)))
                else:
                    out.update(_chosen_ids(v))
        elif isinstance(value, list):
            for item in value:
                out.update(_chosen_ids(item))
        return out

    def _source_name(inp: dict[str, Any], snapshot: dict[str, Any]) -> str | None:
        cards = base.all_visible_cards(snapshot)
        for key in ("sourceCardId", "cardId", "sourceId"):
            cid = inp.get(key)
            if cid and cid in cards:
                name = _name(cards.get(cid))
                if name:
                    return name
        for key in ("sourceCardName", "cardName"):
            if inp.get(key):
                return str(inp[key])
        presentation = inp.get("presentation") or {}
        title = presentation.get("title")
        return str(title)[:240] if title else None

    def telemetry_response(prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int):
        ctx = state.get("ctx")
        if ctx:
            _observe_snapshot(snapshot)
        answer = original_response(prompt, snapshot, deck, player)
        if not ctx:
            return answer

        inp = prompt.get("input") or {}
        ptype = str(inp.get("type") or "")
        clock = _clock(snapshot)
        seat = int(ctx["seat"])

        if player == seat:
            input_summary = {
                "type": ptype,
                "keys": sorted(str(k) for k in inp.keys()),
                "cardName": inp.get("cardName"),
                "cardId": inp.get("cardId") or inp.get("card_id"),
                "manaCost": inp.get("manaCost"),
                "canConfirmFromPool": inp.get("canConfirmFromPool"),
                "presentation": copy.deepcopy(inp.get("presentation") or {}),
            }
            if "mana" in ptype.lower():
                input_summary["actions"] = copy.deepcopy(inp.get("actions") or [])
            if ptype == "chooseAction":
                input_summary["manaActions"] = [
                    copy.deepcopy(a) for a in (inp.get("actions") or [])
                    if a.get("isManaAbility") or a.get("type") == "activateManaAbility"
                ]
            if ptype in {"chooseCards", "revealCards", "chooseFromSelection"}:
                input_summary["cards"] = copy.deepcopy(inp.get("cards") or [])
                input_summary["options"] = copy.deepcopy(inp.get("options") or [])
            _event(
                "promptDecision",
                deck=deck,
                promptType=ptype,
                inputSummary=input_summary,
                chosenOutput=copy.deepcopy((answer or {}).get("output") or {}),
                **clock,
            )

        if deck == "Kinnan" and player == seat and ptype == "payManaCost":
            output = (answer or {}).get("output") or {}
            selected = None
            action_id = str(output.get("actionId") or "")
            if action_id:
                selected = next(
                    (a for a in (inp.get("actions") or []) if str(a.get("id") or "") == action_id),
                    None,
                )
            source_card = runner._action_card(selected, snapshot) if selected else None
            produced = copy.deepcopy((selected or {}).get("producedMana") or [])
            _event(
                "manaPaymentDecision",
                card=str(inp.get("cardName") or ""),
                cardId=str(inp.get("cardId") or inp.get("card_id") or ""),
                manaCost=str(inp.get("manaCost") or ""),
                canConfirmFromPool=bool(inp.get("canConfirmFromPool")),
                decisionType=str(output.get("type") or ""),
                sourceCard=source_card,
                selectedAction=copy.deepcopy(selected),
                producedMana=produced,
                chosenOutput=copy.deepcopy(output),
                manaPoolBefore=_mana_pool(snapshot, seat),
                **clock,
            )

        if deck == "Kinnan" and player == seat and answer is not None:
            visible = base.all_visible_cards(snapshot)
            chosen = _chosen_ids((answer or {}).get("output") or {})
            chosen_cards = []
            for cid in sorted(chosen):
                card_obj = visible.get(cid)
                name = _name(card_obj) if card_obj else ""
                if name:
                    chosen_cards.append({"id": cid, "name": name})
            if chosen_cards:
                _event(
                    "cardSelection",
                    cards=chosen_cards,
                    sourceCard=_source_name(inp, snapshot),
                    promptType=ptype,
                    presentation=copy.deepcopy(inp.get("presentation") or {}),
                    chosenOutput=copy.deepcopy((answer or {}).get("output") or {}),
                    **clock,
                )

        if deck == "Kinnan" and player == seat and ptype == "mulliganPutBack":
            cards = {str(c.get("id") or ""): _name(c) for c in _zone(snapshot, seat, "hand")}
            ids = _chosen_ids((answer or {}).get("output") or {})
            bottomed = [cards[i] for i in ids if i in cards and cards[i]]
            ctx["putBack"].extend(bottomed)
            _event("mulliganPutBack", cards=bottomed, handBefore=_hand_names(snapshot, seat), **clock)

        if ptype == "chooseAction":
            output = (answer or {}).get("output") or {}
            if output.get("type") == "act" and output.get("actionId"):
                aid = str(output.get("actionId"))
                action = next((a for a in (inp.get("actions") or []) if str(a.get("id") or "") == aid), None)
                if action:
                    card = runner._action_card(action, snapshot)
                    atype = str(action.get("type") or "")
                    info = {
                        "card": card,
                        "actionType": atype,
                        "description": str(action.get("description") or action.get("label") or "")[:320],
                        "player": int(player),
                        # Preserve the selected action and answer as a durable
                        # machine-readable trace.  This is required for exact
                        # tutor, reveal, activation and mana attribution; a
                        # human-readable description alone is not sufficient.
                        "rawAction": copy.deepcopy(action),
                        "chosenOutput": copy.deepcopy(output),
                        "rawCard": copy.deepcopy((base.all_visible_cards(snapshot) or {}).get(str(action.get("cardId") or "")) or {}),
                        **clock,
                    }
                    if deck == "Kinnan" and player == seat and card:
                        pin, pbf = _protection_context(snapshot, seat, card)
                        info.update({
                            "handBefore": _hand_names(snapshot, seat),
                            "battlefieldBefore": _battlefield_names(snapshot, seat),
                            "protectionInHand": pin,
                            "protectionOnBattlefield": pbf,
                            "hasProtection": bool(pin or pbf),
                            "manaPool": _mana_pool(snapshot, seat),
                        })
                        _event("actionChosen", **info)
                    elif player != seat:
                        ctx["lastOpponentAction"] = info
                        _event("opponentAction", **info)

        if "target" in ptype.lower() and answer is not None:
            visible = base.all_visible_cards(snapshot)
            chosen = _chosen_ids((answer or {}).get("output") or {})
            for cid in chosen:
                card = visible.get(cid)
                if not card:
                    continue
                controller = str(card.get("controllerId") or "")
                owner = str(card.get("ownerId") or "")
                if controller != f"player-{seat}" and owner != f"player-{seat}":
                    continue
                target_name = _name(card)
                if not target_name:
                    continue
                _event(
                    "targeted", targetCard=target_name, targetCardId=cid,
                    byPlayer=int(player), hostile=bool(player != seat),
                    sourceCard=_source_name(inp, snapshot), promptType=ptype,
                    handAtInteraction=_hand_names(snapshot, seat), **clock,
                )
        return answer

    base.response_for = telemetry_response

    original_run = runner.run_game
    def telemetry_run_game(*args: Any, **kwargs: Any) -> dict[str, Any]:
        seat = _seat_from_args(args, kwargs)
        ctx = {
            "seat": seat, "seq": 0, "events": [], "mulliganHands": [],
            "putBack": [], "keptHand": None, "firstVisibleHand": None,
            "zones": {}, "lastOpponentAction": None,
        }
        state["ctx"] = ctx
        try:
            result = original_run(*args, **kwargs)
            result["cardTelemetryVersion"] = "card-telemetry-v1"
            result["cardTelemetry"] = {
                "openingHand": ctx.get("mulliganHands", [{}])[0].get("cards", []) if ctx.get("mulliganHands") else (ctx.get("firstVisibleHand") or []),
                "keptHand": ctx.get("keptHand") or [],
                "mulliganHands": ctx.get("mulliganHands") or [],
                "putBackCards": ctx.get("putBack") or [],
                "events": ctx.get("events") or [],
            }
            return result
        finally:
            state["ctx"] = None

    runner.run_game = telemetry_run_game
