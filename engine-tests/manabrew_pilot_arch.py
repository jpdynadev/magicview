#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import manabrew_pilot as base
import manabrew_pilot_v7 as v7
import manabrew_pilot_v8 as runner
import kinnan_policy_v8 as policy

runner.PILOT_VERSION = 'arch-aware-v1.4'

# Cards introduced by mutation experiments must not silently fall through to the
# legacy unknown-card score of 2. Future experiment generators should fail when
# an added card is not registered here.
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
    # Druid/Effigy architecture
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
_ORIGINAL_ACTION_SCORE = runner.v8_action_score
_ORIGINAL_PAYMENT = runner.choose_productive_payment_v8
_ORIGINAL_CONFIGURE_DECKS = runner.configure_decks

# Guard payment actions by the exact Forge-advertised payment state. A mana
# ability may be retried after the legal-action set changes (for example after a
# source taps), but the same action cannot be selected forever against an
# unchanged payManaCost prompt. This distinguishes semantic pilot livelock from
# protocol staleness without inventing mana or bypassing Forge legality.
_PAYMENT_ACTION_COUNTS: dict[tuple[Any, ...], int] = {}
PAYMENT_ACTION_REPEAT_LIMIT = 2


def _payment_signature(inp: dict[str, Any], player: int, action_id: str) -> tuple[Any, ...]:
    legal_ids = tuple(sorted(str(action.get('id')) for action in (inp.get('actions') or []) if action.get('id')))
    return (
        player,
        str(inp.get('cardId') or ''),
        str(inp.get('cardName') or ''),
        str(inp.get('manaCost') or ''),
        legal_ids,
        str(action_id),
    )


def configure_decks(variant: str, kinnan_seat: int):
    _PAYMENT_ACTION_COUNTS.clear()
    return _ORIGINAL_CONFIGURE_DECKS(variant, kinnan_seat)


runner.configure_decks = configure_decks


def hand_score(deck: str, name: str) -> int:
    if deck == 'Kinnan' and name in ROLE_SCORES:
        return ROLE_SCORES[name]
    return _ORIGINAL_HAND_SCORE(deck, name)


base.hand_score = hand_score
base.K_TUTORS.update(TUTOR_ADDS)
# Mirage Mirror has a strategically meaningful activated ability; without this,
# v7 assigns unknown activators a large negative score and effectively blanks it.
v7.KNOWN_GOOD_ACTIVATORS.add('Mirage Mirror')


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


def action_score(deck: str, action: dict[str, Any], snapshot: dict[str, Any], player: int) -> int:
    score = _ORIGINAL_ACTION_SCORE(deck, action, snapshot, player)
    if deck != 'Kinnan':
        return score
    name = runner._action_card(action, snapshot)
    text = str(action.get('description') or action.get('label') or '')
    lowered = text.lower()

    # A bare Grim Monolith untap is mana-neutral even with Kinnan and becomes a
    # deterministic two-state livelock when Basalt pays to untap Grim and Grim
    # then pays to untap Basalt. Forge correctly advertises both legal actions;
    # the strategic policy must decline the zero-gain Grim half of that cycle.
    # Basalt's {3} untap remains untouched because Kinnan + Basalt is the actual
    # positive-mana deterministic engine.
    if (
        name == 'Grim Monolith'
        and action.get('type') == 'activateAbility'
        and 'untap this artifact' in lowered
    ):
        return -5000

    if name == 'Mirage Mirror' and action.get('type') == 'activateAbility':
        if 'copy' in lowered:
            own_turn = snapshot.get('activePlayerId') == f'player-{player}'
            own_main = own_turn and snapshot.get('step') in {'main1', 'main2'}
            return 1125 if own_main else 350
    return score


runner.v8_action_score = action_score
base.action_score = action_score


def _guard_payment_answer(inp: dict[str, Any], player: int, answer: dict[str, Any], canceled: bool):
    output = (answer or {}).get('output') or {}
    if canceled or output.get('type') != 'act' or not output.get('actionId'):
        return answer, canceled
    action_id = str(output['actionId'])
    key = _payment_signature(inp, player, action_id)
    count = _PAYMENT_ACTION_COUNTS.get(key, 0)
    if count < PAYMENT_ACTION_REPEAT_LIMIT:
        _PAYMENT_ACTION_COUNTS[key] = count + 1
        return answer, False

    # Remove only the repeating action from this exact payment state and ask the
    # existing color-aware policy whether another Forge-advertised action can pay.
    filtered = dict(inp)
    filtered['actions'] = [
        action for action in (inp.get('actions') or [])
        if str(action.get('id') or '') != action_id
    ]
    retry, retry_canceled = _ORIGINAL_PAYMENT(filtered, player)
    retry_output = (retry or {}).get('output') or {}
    if not retry_canceled and retry_output.get('type') == 'act' and retry_output.get('actionId'):
        retry_id = str(retry_output['actionId'])
        retry_key = _payment_signature(filtered, player, retry_id)
        retry_count = _PAYMENT_ACTION_COUNTS.get(retry_key, 0)
        if retry_count < PAYMENT_ACTION_REPEAT_LIMIT:
            _PAYMENT_ACTION_COUNTS[retry_key] = retry_count + 1
            return retry, False
    return {'type': 'payManaCost', 'output': {'type': 'cancel'}}, True


def choose_productive_payment(inp: dict[str, Any], player: int) -> tuple[dict[str, Any], bool]:
    """Use Forge-advertised mana abilities, with a same-state livelock guard.

    v8's color-aware payment helper can reject flexible sources when the payment
    prompt labels the action only by permanent name (for example Arcane Signet or
    Fellwar Stone) instead of embedding the produced colors. Forge remains the
    legality authority: this fallback chooses only actions advertised in the
    active payManaCost prompt, while the repeat guard prevents selecting the same
    payment action forever when Forge's payment state does not change.
    """
    answer, canceled = _ORIGINAL_PAYMENT(inp, player)
    if not canceled:
        return _guard_payment_answer(inp, player, answer, False)

    mana_actions = [
        action for action in (inp.get('actions') or [])
        if action.get('id') and action.get('type') in {'activateManaAbility', 'activateAbility'}
    ]
    runner.PAYMENT_COLOR_PREFERENCES[player] = policy.required_payment_colors(inp)
    for chosen in mana_actions:
        action_id = str(chosen['id'])
        key = _payment_signature(inp, player, action_id)
        if _PAYMENT_ACTION_COUNTS.get(key, 0) >= PAYMENT_ACTION_REPEAT_LIMIT:
            continue
        _PAYMENT_ACTION_COUNTS[key] = _PAYMENT_ACTION_COUNTS.get(key, 0) + 1
        return {
            'type': 'payManaCost',
            'output': {'type': 'act', 'actionId': chosen['id']},
        }, False

    runner.PAYMENT_COLOR_PREFERENCES.pop(player, None)
    return {'type': 'payManaCost', 'output': {'type': 'cancel'}}, True


runner.choose_productive_payment_v8 = choose_productive_payment


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
    # Do not inspect candidates themselves: otherwise the mere presence of a
    # clone on the battlefield could make an unrelated targeting prompt look
    # like a copy prompt.
    context = {
        key: inp.get(key)
        for key in ('cardName', 'sourceCardName', 'description', 'label', 'presentation', 'abilityText')
        if key in inp
    }
    raw = json.dumps(context, sort_keys=True).lower()
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