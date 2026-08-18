#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import manabrew_pilot as base
import manabrew_pilot_v8 as runner

runner.PILOT_VERSION = 'arch-aware-v1'

# Cards introduced by mutation experiments must not silently fall through to the
# legacy unknown-card score of 2. Keep this registry small and explicit; future
# experiment generators should fail when an added card is not registered here.
ROLE_SCORES = {
    # F10 tutor package
    'Reshape': 9,
    'Trinket Mage': 8,
    "Green Sun's Zenith": 9,
    'Eldritch Evolution': 9,
    'Spellseeker': 8,
    'Mystical Tutor': 9,
    'Tribute Mage': 8,
    # Copy/clone architecture
    'Copy Enchantment': 8,
    'Copy Artifact': 9,
    'Flesh Duplicate': 8,
    'Mirage Mirror': 8,
    'Clever Impersonator': 8,
    'Gene Pollinator': 8,
    'Phyrexian Metamorph': 8,
    # Druid/Effigy architecture (legacy pilot already knows Druid/Effigy, kept
    # here so the experiment validator has one source of truth).
    'Devoted Druid': 10,
    "Machine God's Effigy": 8,
}

TUTOR_ADDS = {
    'Reshape', 'Trinket Mage', "Green Sun's Zenith", 'Eldritch Evolution',
    'Spellseeker', 'Mystical Tutor', 'Tribute Mage',
}
COPY_CARDS = {
    'Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Mirage Mirror',
    'Clever Impersonator', 'Gene Pollinator', 'Phyrexian Metamorph', 'Mockingbird',
}

_ORIGINAL_HAND_SCORE = base.hand_score
_ORIGINAL_KEEP_PRIORITY = runner._keep_priority
_ORIGINAL_SMART_RESPONSE = runner.smart_response


def hand_score(deck: str, name: str) -> int:
    if deck == 'Kinnan' and name in ROLE_SCORES:
        return ROLE_SCORES[name]
    return _ORIGINAL_HAND_SCORE(deck, name)


base.hand_score = hand_score
base.K_TUTORS.update(TUTOR_ADDS)


def keep_priority(name: str) -> int:
    if name in TUTOR_ADDS:
        return 108
    if name in COPY_CARDS:
        return 82
    if name == 'Devoted Druid':
        return 96
    if name == "Machine God's Effigy":
        return 94
    return _ORIGINAL_KEEP_PRIORITY(name)


runner._keep_priority = keep_priority


def _copy_target_score(name: str, controller: str | None, player: int) -> int:
    own = controller == f'player-{player}'
    # Prefer deterministic/self-contained targets first, then high-value engines
    # from either side of the table. Legal candidate filtering remains Forge's.
    self_scores = {
        'Basalt Monolith': 220, 'Kinnan, Bonder Prodigy': 215,
        'Devoted Druid': 210, 'Grim Monolith': 190, 'Bloom Tender': 175,
        'Forensic Gadgeteer': 165, 'Rhystic Study': 160, 'Mystic Remora': 155,
        'The One Ring': 150, 'Mana Vault': 145, 'Sol Ring': 130,
        'Sylvan Library': 125, 'Talisman of Curiosity': 115,
    }
    opp_scores = {
        'Rhystic Study': 170, 'Mystic Remora': 165, 'The One Ring': 155,
        'Talion, the Kindly Lord': 150, 'Esper Sentinel': 140,
        'Mana Vault': 135, 'Sol Ring': 125, 'Bloom Tender': 120,
    }
    if own:
        return self_scores.get(name, 80)
    return opp_scores.get(name, 55)


def _copy_prompt(inp: dict[str, Any]) -> bool:
    raw = json.dumps(inp, sort_keys=True).lower()
    return 'copy' in raw or any(name.lower() in raw for name in COPY_CARDS)


def smart_response(prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int):
    inp = prompt.get('input') or {}
    if deck == 'Kinnan' and inp.get('type') == 'chooseBoardTargets' and _copy_prompt(inp):
        cards = base.all_visible_cards(snapshot)
        candidates = inp.get('candidates', []) or []
        minimum = int(inp.get('minTargets', 1) or 1)
        maximum = max(minimum, int(inp.get('maxTargets', 1) or 1))
        scored = []
        for ref in candidates:
            if ref.get('kind') != 'card':
                continue
            card = cards.get(ref.get('id'), {})
            scored.append((_copy_target_score(base.card_name(card), card.get('controllerId'), player), ref))
        scored.sort(key=lambda item: item[0], reverse=True)
        chosen = [ref for _, ref in scored[:maximum]]
        if len(chosen) >= minimum:
            return {'type': 'chooseBoardTargets', 'output': {'type': 'boardTargets', 'chosen': chosen}}
    return _ORIGINAL_SMART_RESPONSE(prompt, snapshot, deck, player)


base.response_for = smart_response

# Load any generated architecture decks.
deck_dir = Path(__file__).resolve().parent / 'decks'
for path in sorted(deck_dir.glob('Kinnan_ARCH_*.dck')):
    key = path.stem.replace('Kinnan_ARCH_', '', 1)
    runner.VARIANT_FILES[key] = path.name


if __name__ == '__main__':
    raise SystemExit(runner.main())
