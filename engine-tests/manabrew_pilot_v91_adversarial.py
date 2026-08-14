#!/usr/bin/env python3
"""Adversarial cEDH policy overlay for finalist stress tests.

Forge/Manabrew remains the rules authority. This layer only ranks legal actions.
It makes opponent decks race their own compact wins, preserve interaction when a
rival is threatening a win, and preferentially disrupt Kinnan's critical pieces.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import manabrew_pilot as base
import manabrew_pilot_v7 as v7
import manabrew_pilot_v8 as runner
import manabrew_pilot_v89  # patches corrected attempt metrics into runner

runner.PILOT_VERSION = "v9.1.0-adversarial"

DECK_DIR = Path(__file__).resolve().parent / "decks"
for deck_path in sorted(DECK_DIR.glob("Kinnan_M2K*.dck")):
    runner.VARIANT_FILES[deck_path.stem.replace("Kinnan_", "", 1)] = deck_path.name

POD_PROFILES = {
    "balanced": [("RogSi", "RogSi_2026.dck"), ("Blue Farm", "Blue_Farm_2026.dck"), ("RogThras", "RogThras_2026.dck")],
    "turbo": [("RogSi", "RogSi_2026.dck"), ("RogSi", "RogSi_2026.dck"), ("Blue Farm", "Blue_Farm_2026.dck")],
    "midrange": [("Blue Farm", "Blue_Farm_2026.dck"), ("Blue Farm", "Blue_Farm_2026.dck"), ("RogThras", "RogThras_2026.dck")],
    "mixed": [("RogSi", "RogSi_2026.dck"), ("RogThras", "RogThras_2026.dck"), ("Blue Farm", "Blue_Farm_2026.dck")],
}
POD = os.environ.get("CEDH_POD", "balanced")
if POD not in POD_PROFILES:
    raise RuntimeError(f"unknown CEDH_POD={POD}; choose {sorted(POD_PROFILES)}")

TRUE_STACK_INTERACTION = {
    "Force of Will", "Fierce Guardianship", "Pact of Negation", "Flusterstorm", "Swan Song",
    "An Offer You Can't Refuse", "Mental Misstep", "Mindbreak Trap", "Daze", "Pyroblast",
    "Red Elemental Blast", "Deflecting Swat", "Mana Drain", "Delay", "Spell Pierce", "Miscast",
}
REMOVAL = {"Deadly Rollick", "Chain of Vapor", "Into the Flood Maw", "Snap", "Abrupt Decay", "Assassin's Trophy", "Nature's Claim"}
ROGSI_WINS = {"Underworld Breach", "Lion's Eye Diamond", "Brain Freeze", "Thassa's Oracle", "Demonic Consultation", "Tainted Pact", "Ad Nauseam"}
FARM_WINS = {"Thassa's Oracle", "Demonic Consultation", "Tainted Pact", "Ad Nauseam"}
K_CRITICAL = {
    "Kinnan, Bonder Prodigy", "Basalt Monolith", "Grim Monolith", "Power Artifact",
    "Forensic Gadgeteer", "Staff of Domination", "Thrasios, Triton Hero", "Walking Ballista",
    "Tezzeret the Seeker", "Transmute Artifact", "Fabricate", "Whir of Invention", "Reshape",
}

_original_keep = base.keep_hand
_original_score = base.action_score
_original_target = base.target_ref_score
_original_configure = runner.configure_decks


def configure_decks(variant: str, kinnan_seat: int):
    if variant not in runner.VARIANT_FILES:
        raise ValueError(f"unknown variant {variant}")
    runner.CURRENT_KINNAN_SEAT = kinnan_seat
    opponents = list(POD_PROFILES[POD])
    ordered = opponents[:]
    ordered.insert(kinnan_seat, ("Kinnan", runner.VARIANT_FILES[variant]))
    base.DECKS = ordered
    import manabrew_pilot_v3 as v3
    v3.DECKS = ordered
    return ordered

runner.configure_decks = configure_decks


def names(snapshot: dict[str, Any], seat: int, zone: str) -> set[str]:
    return {base.card_name(c) for c in base.zone_cards(snapshot, seat, zone)}


def kinnan_threat(snapshot: dict[str, Any]) -> int:
    k = runner.CURRENT_KINNAN_SEAT
    bf, hand = names(snapshot, k, "battlefield"), names(snapshot, k, "hand")
    stack = json.dumps(snapshot.get("stack", []) or []).lower()
    score = 0
    if "Kinnan, Bonder Prodigy" in bf: score += 2
    if "Basalt Monolith" in bf or "Grim Monolith" in bf: score += 2
    if "Power Artifact" in bf or "Forensic Gadgeteer" in bf: score += 2
    if {"Kinnan, Bonder Prodigy", "Basalt Monolith"} <= bf: score += 6
    if {"Basalt Monolith", "Power Artifact"} <= bf: score += 6
    if {"Kinnan, Bonder Prodigy", "Grim Monolith", "Forensic Gadgeteer"} <= bf: score += 6
    if (bf | hand) & {"Staff of Domination", "Thrasios, Triton Hero", "Walking Ballista"}: score += 2
    if any(x.lower() in stack for x in K_CRITICAL): score += 5
    if any(x in stack for x in ("finale of devastation", "transmute artifact", "tezzeret the seeker", "resha", "whir of invention")): score += 3
    return score


def rival_win_on_stack(snapshot: dict[str, Any], player: int) -> bool:
    raw = json.dumps(snapshot.get("stack", []) or []).lower()
    win_tokens = ["thassa", "demonic consultation", "tainted pact", "underworld breach", "brain freeze", "ad nauseam"]
    return any(t in raw for t in win_tokens) or kinnan_threat(snapshot) >= 7


def own_win_ready(deck: str, snapshot: dict[str, Any], player: int) -> bool:
    pool = names(snapshot, player, "hand") | names(snapshot, player, "battlefield") | names(snapshot, player, "graveyard")
    if deck == "RogSi":
        oracle = "Thassa's Oracle" in pool and bool(pool & {"Demonic Consultation", "Tainted Pact"})
        breach = "Underworld Breach" in pool and "Lion's Eye Diamond" in pool and "Brain Freeze" in pool
        return oracle or breach
    if deck == "Blue Farm":
        return "Thassa's Oracle" in pool and bool(pool & {"Demonic Consultation", "Tainted Pact"})
    return False


def adversarial_keep(deck: str, hand: list[dict[str, Any]], mull: int) -> bool:
    if deck == "Kinnan":
        return _original_keep(deck, hand, mull)
    ns = {base.card_name(c) for c in hand}
    lands = sum(n in base.LANDS for n in ns)
    mana = sum(n in base.FAST_MANA for n in ns)
    interaction = bool(ns & (TRUE_STACK_INTERACTION | REMOVAL))
    if mull >= 3:
        return lands >= 1 and lands + mana >= 2
    if deck == "RogSi":
        plan = bool(ns & (base.R_TUTORS | ROGSI_WINS))
        return lands >= 1 and lands + mana >= 2 and plan and (mull >= 2 or interaction or bool(ns & {"Ad Nauseam", "Underworld Breach", "Necropotence"}))
    if deck == "Blue Farm":
        plan = bool(ns & (base.R_TUTORS | FARM_WINS | {"Mystic Remora", "Rhystic Study", "Tymna the Weaver"}))
        return lands >= 1 and lands + mana >= 2 and plan and (interaction or mull >= 2)
    if deck == "RogThras":
        plan = bool(ns & {"Mystic Remora", "Rhystic Study", "Thrasios, Triton Hero"}) or interaction
        return lands >= 1 and lands + mana >= 2 and plan
    return _original_keep(deck, hand, mull)

base.keep_hand = adversarial_keep


def adversarial_score(deck: str, action: dict[str, Any], snapshot: dict[str, Any], player: int) -> int:
    score = _original_score(deck, action, snapshot, player)
    if deck == "Kinnan":
        return score
    card_id = action.get("cardId") or action.get("card_id")
    card = base.all_visible_cards(snapshot).get(card_id, {})
    name = base.card_name(card)
    typ = action.get("type", "")
    own_turn = snapshot.get("activePlayerId") == f"player-{player}"
    own_main = own_turn and snapshot.get("step") in {"main1", "main2"}
    stack_live = bool(snapshot.get("stack"))
    threat = kinnan_threat(snapshot)
    ready = own_win_ready(deck, snapshot, player)

    # If this deck can present a win, race instead of durdling.
    if typ == "cast" and own_main and ready:
        if deck == "RogSi" and name in ROGSI_WINS: score += 2600
        if deck == "Blue Farm" and name in FARM_WINS: score += 2500
        if name in base.R_TUTORS: score += 1800

    # Preserve/react with stack interaction specifically for real win threats.
    if typ == "cast" and name in TRUE_STACK_INTERACTION:
        if stack_live and rival_win_on_stack(snapshot, player): return max(score, 4200 + threat * 80)
        if stack_live: return max(score, 450)
        return min(score, -900)  # don't fire protection/counters into empty stack

    if typ == "cast" and name in REMOVAL:
        if threat >= 5: return max(score, 2600 + threat * 70)
        if stack_live: return max(score, 900)

    # Archetype-specific proactive priorities.
    if typ == "cast" and own_main:
        if deck == "RogSi":
            if name in base.R_TUTORS: score += 900
            if name in {"Ad Nauseam", "Underworld Breach", "Necropotence"}: score += 1100
            if name in {"Thassa's Oracle", "Demonic Consultation", "Tainted Pact"}: score += 1000
        elif deck == "Blue Farm":
            if name in {"Mystic Remora", "Rhystic Study", "Tymna the Weaver"}: score += 650
            if name in base.R_TUTORS: score += 700
            if name in FARM_WINS: score += 900
        elif deck == "RogThras":
            if name in {"Mystic Remora", "Rhystic Study", "Thrasios, Triton Hero"}: score += 700

    # When Kinnan is one piece away, interaction outranks medium development.
    if threat >= 7 and not ready and typ == "cast" and name not in TRUE_STACK_INTERACTION | REMOVAL:
        score -= 500
    return score

base.action_score = adversarial_score


def adversarial_target(deck: str, ref: dict[str, Any], snapshot: dict[str, Any], player: int, hostile: bool = False) -> int:
    score = _original_target(deck, ref, snapshot, player, hostile)
    if deck == "Kinnan" or not hostile or ref.get("kind") != "card":
        return score
    card = base.all_visible_cards(snapshot).get(ref.get("id"), {})
    name = base.card_name(card)
    ctrl = card.get("controllerId")
    if ctrl == f"player-{runner.CURRENT_KINNAN_SEAT}":
        priority = {
            "Basalt Monolith": 5000, "Power Artifact": 4900, "Kinnan, Bonder Prodigy": 4700,
            "Grim Monolith": 4550, "Forensic Gadgeteer": 4500, "Staff of Domination": 4400,
            "Thrasios, Triton Hero": 4300, "Tezzeret the Seeker": 4100,
        }
        return priority.get(name, max(score, 1200 if name in K_CRITICAL else 300))
    # Other players' compact wins are also valid disruption targets.
    if name in ROGSI_WINS | FARM_WINS:
        return max(score, 3600)
    return score

base.target_ref_score = adversarial_target

if __name__ == "__main__":
    raise SystemExit(runner.main())
