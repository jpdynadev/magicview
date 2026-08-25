#!/usr/bin/env python3
"""Apply v1.20 source-assignment repair for Kinnan's {5}{G}{U} payment.

v1.19 prioritized colored mana but could still spend the only flexible G/U
source on one pip when both G and U were missing.  The canonical Logan key
seat=1 seed=5010140 then had no second physical source for the other pip,
cancelled payment, and retried Kinnan until idle timeout.

v1.20 treats missing colored pips as a physical-source assignment problem before
spending any source.  If both G and U are missing, payment proceeds only when
one advertised mana action produces both colors simultaneously or two distinct
physical sources can cover G and U.  Flexible alternatives on one permanent are
not counted twice.  Forge remains the legality/payment authority.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.20-adversarial" in text and "_v120_kinnan_payment_response" in text:
    print('v1.20 Kinnan colored source-assignment repair already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.19-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.19 pilot identity not found; apply v1.12-v1.19 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.20-adversarial'", 1)

append = r'''

# v1.20: require a real physical-source assignment for missing G/U before
# spending the first colored source.
_V119_RESPONSE = runner.base.response_for


def _v120_explicit_color_actions(inp: dict[str, Any], wanted: str) -> list[dict[str, Any]]:
    wanted = _v118_color_token(wanted)
    out: list[dict[str, Any]] = []
    for action in inp.get('actions', []) or []:
        if not (action.get('isManaAbility') or action.get('type') == 'activateManaAbility'):
            continue
        if not action.get('id') or not (action.get('cardId') or action.get('card_id')):
            continue
        colors: set[str] = set()
        for item in action.get('producedMana') or []:
            try:
                amount = max(0, int((item or {}).get('amount') or 0))
            except (AttributeError, TypeError, ValueError):
                amount = 0
            if amount > 0:
                colors.add(_v118_color_token((item or {}).get('color')))
        if wanted in colors:
            out.append(action)
    return sorted(out, key=lambda a: str(a.get('id')))


def _v120_action_colors(action: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in action.get('producedMana') or []:
        try:
            amount = max(0, int((item or {}).get('amount') or 0))
        except (AttributeError, TypeError, ValueError):
            amount = 0
        if amount <= 0:
            continue
        color = _v118_color_token((item or {}).get('color'))
        out[color] = out.get(color, 0) + amount
    return out


def _v120_choose_safe_colored_action(inp: dict[str, Any], missing: list[str]) -> dict[str, Any] | None:
    if not missing:
        return None
    if len(missing) == 1:
        actions = _v120_explicit_color_actions(inp, missing[0])
        return actions[0] if actions else None

    # Both G and U are missing.  First allow a *single action* that actually
    # produces both pips simultaneously (not two alternative choices on one card).
    joint: list[dict[str, Any]] = []
    for action in inp.get('actions', []) or []:
        colors = _v120_action_colors(action)
        if colors.get('G', 0) >= 1 and colors.get('U', 0) >= 1 and action.get('id'):
            joint.append(action)
    if joint:
        return sorted(joint, key=lambda a: str(a.get('id')))[0]

    green = _v120_explicit_color_actions(inp, 'G')
    blue = _v120_explicit_color_actions(inp, 'U')
    pairs: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for ga in green:
        gsrc = str(ga.get('cardId') or ga.get('card_id') or '')
        for ua in blue:
            usrc = str(ua.get('cardId') or ua.get('card_id') or '')
            if gsrc and usrc and gsrc != usrc:
                pairs.append((str(ga.get('id')), str(ua.get('id')), ga, ua))
    if not pairs:
        return None
    pairs.sort(key=lambda x: (x[0], x[1]))
    # Spend the G-assigned source first; on the next prompt the U source remains.
    return pairs[0][2]


def _v120_kinnan_payment_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    inp = prompt.get('input') or {}
    if deck != 'Kinnan' or inp.get('type') != 'payManaCost':
        return _V119_RESPONSE(prompt, snapshot, deck, player)

    card_name = str(inp.get('cardName') or '')
    cost = str(inp.get('manaCost') or '').replace(' ', '').upper()
    if card_name != 'Kinnan, Bonder Prodigy' or ('{5}{G}{U}' not in cost and '{5}{U}{G}' not in cost):
        return _V119_RESPONSE(prompt, snapshot, deck, player)
    if bool(inp.get('canConfirmFromPool')):
        return _V119_RESPONSE(prompt, snapshot, deck, player)

    floating = _v118_floating_mana(snapshot, player)
    missing: list[str] = []
    if floating.get('G', 0) < 1:
        missing.append('G')
    if floating.get('U', 0) < 1:
        missing.append('U')

    if missing:
        action = _v120_choose_safe_colored_action(inp, missing)
        if action is None:
            return {'type': 'payManaCost', 'output': {'type': 'cancel'}}
        return {
            'type': 'payManaCost',
            'output': {'type': 'act', 'actionId': action['id']},
        }

    return _V119_RESPONSE(prompt, snapshot, deck, player)


runner.base.response_for = _v120_kinnan_payment_response
arch.base.response_for = _v120_kinnan_payment_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.20-adversarial Kinnan colored source-assignment repair')
