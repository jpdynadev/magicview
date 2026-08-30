#!/usr/bin/env python3
"""Apply v1.19 Kinnan colored-payment ordering repair.

v1.18 correctly rejected many impossible {5}{G}{U} activations, but canonical
Logan key seat=1 seed=5010140 still reproduced an idle loop when the activation
was feasible only if an already-floating colored pip was preserved.  The generic
payment policy could spend that colored mana toward the five generic first,
then tap Waterlogged Grove for the other color, leaving no source for the first
colored pip and cancelling payment.

v1.19 is narrowly scoped to Kinnan's own payManaCost prompt.  Before delegating
to the existing payment policy, it preserves/pays the required G and U pips:
- if G is not currently floating, choose an explicitly advertised G source;
- if U is not currently floating, choose an explicitly advertised U source;
- if a required color is missing and no explicit source can supply it, cancel
  immediately instead of spending generic/ambiguous sources;
- once both G and U are floating (or Forge says the pool can confirm), delegate
  unchanged to the validated payment policy for the five generic.

Unspecified mana sources such as Fellwar Stone are never invented as G/U; they
remain available for generic payment after both colored pips are secured. Forge
remains the legality/payment authority.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.19-adversarial" in text and "_v119_kinnan_payment_response" in text:
    print('v1.19 Kinnan colored-payment repair already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.18-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.18 pilot identity not found; apply v1.12-v1.18 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.19-adversarial'", 1)

append = r'''

# v1.19: preserve/pay Kinnan's colored pips before generic mana.
_V118_RESPONSE = runner.base.response_for


def _v119_explicit_color_action(inp: dict[str, Any], wanted: str) -> dict[str, Any] | None:
    wanted = _v118_color_token(wanted)
    candidates: list[tuple[str, dict[str, Any]]] = []
    for action in inp.get('actions', []) or []:
        if not (action.get('isManaAbility') or action.get('type') == 'activateManaAbility'):
            continue
        colors: set[str] = set()
        for item in action.get('producedMana') or []:
            try:
                amount = max(0, int((item or {}).get('amount') or 0))
            except (AttributeError, TypeError, ValueError):
                amount = 0
            if amount > 0:
                colors.add(_v118_color_token((item or {}).get('color')))
        if wanted in colors and action.get('id'):
            # Stable choice for deterministic paired runs.
            candidates.append((str(action.get('id')), action))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _v119_kinnan_payment_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    inp = prompt.get('input') or {}
    if deck != 'Kinnan' or inp.get('type') != 'payManaCost':
        return _V118_RESPONSE(prompt, snapshot, deck, player)

    card_name = str(inp.get('cardName') or '')
    cost = str(inp.get('manaCost') or '').replace(' ', '').upper()
    if card_name != 'Kinnan, Bonder Prodigy' or ('{5}{G}{U}' not in cost and '{5}{U}{G}' not in cost):
        return _V118_RESPONSE(prompt, snapshot, deck, player)

    # If Forge can already confirm from the floating pool, preserve the normal
    # payment policy and let it submit the confirmation.
    if bool(inp.get('canConfirmFromPool')):
        return _V118_RESPONSE(prompt, snapshot, deck, player)

    floating = _v118_floating_mana(snapshot, player)
    missing: list[str] = []
    if floating.get('G', 0) < 1:
        missing.append('G')
    if floating.get('U', 0) < 1:
        missing.append('U')

    # Pay a missing colored pip before touching any generic/ambiguous source.
    for wanted in missing:
        action = _v119_explicit_color_action(inp, wanted)
        if action is not None:
            return {
                'type': 'payManaCost',
                'output': {'type': 'act', 'actionId': action['id']},
            }

    # A required colored pip is still missing and no explicit source can make it.
    # Cancel without tapping generic sources; the v1.18 chooseAction guard and
    # recurrence protections can then select a different strategic action.
    if missing:
        return {'type': 'payManaCost', 'output': {'type': 'cancel'}}

    return _V118_RESPONSE(prompt, snapshot, deck, player)


runner.base.response_for = _v119_kinnan_payment_response
arch.base.response_for = _v119_kinnan_payment_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.19-adversarial Kinnan colored-payment priority repair')
