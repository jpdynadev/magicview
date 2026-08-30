#!/usr/bin/env python3
"""Apply the narrow v1.12 Kinnan payment-progress repair to the arch pilot.

v1.11 prevented obviously unaffordable Kinnan activations using an optimistic
pre-action mana bound.  A canonical F10 replay still showed a false-positive:
Forge advertised the activation, then its authoritative payManaCost prompt had
canConfirmFromPool=false and remaining free mana abilities, while the legacy
payment chooser returned cancel.  Cancelling this activated ability can strand
Forge in a no-progress state.

v1.12 does not change Forge legality or invent mana.  It only intercepts a
legacy `cancel` for Kinnan's {5}{G}{U} payment while Forge is still advertising
zero-input mana abilities, and consumes one such engine-advertised source.
When no productive source remains, the original cancel is preserved.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()
if "arch-aware-v1.12-adversarial" in text and "_v112_productive_kinnan_payment" in text:
    print('v1.12 payment repair already applied')
    raise SystemExit(0)

old = "runner.PILOT_VERSION = 'arch-aware-v1.11-adversarial'"
if old not in text:
    raise SystemExit('expected v1.11 pilot identity not found')
text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.12-adversarial'", 1)

append = r'''

# v1.12: Forge remains the payment/legality authority.  If the legacy payment
# policy wants to cancel Kinnan's seven-mana activation even though the
# authoritative payManaCost prompt is still advertising free mana abilities,
# consume one advertised source first.  This is deliberately scoped to the
# Kinnan activation and only overrides a would-be cancel.
_V111_PAYMENT = runner.choose_productive_payment_v8


def _v112_productive_kinnan_payment(inp: dict[str, Any], player: int):
    answer, canceled = _V111_PAYMENT(inp, player)
    if not canceled:
        return answer, canceled
    if str(inp.get('cardName') or '') != 'Kinnan, Bonder Prodigy':
        return answer, canceled
    normalized = str(inp.get('manaCost') or '').replace(' ', '').upper()
    if normalized not in {'{5}{G}{U}', '{5}{U}{G}'}:
        return answer, canceled

    actions = []
    for action in inp.get('actions', []) or []:
        if action.get('type') != 'activateManaAbility' or not action.get('isManaAbility'):
            continue
        cost = str(action.get('cost') or '').replace(' ', '').upper()
        # Only use sources Forge advertises without an additional mana payment.
        # Tap/life/sacrifice costs remain Forge-owned and are legal advertised
        # payment actions; mana-bearing costs would risk a non-progress filter.
        if any(token in cost for token in ('{0}', '{1}', '{2}', '{3}', '{4}', '{5}', '{W}', '{U}', '{B}', '{R}', '{G}', '{C}', '{X}')):
            continue
        actions.append(action)
    if not actions:
        return answer, canceled

    required = set(policy.required_payment_colors(inp))

    def score(action: dict[str, Any]):
        produced = {
            str(item.get('color') or '').upper()
            for item in (action.get('producedMana') or [])
        }
        description = ' '.join(
            str(action.get(key) or '')
            for key in ('description', 'label', 'cardName')
        ).lower()
        flexible = any(token in description for token in (
            'any color', 'chrome mox', 'mox diamond', 'command tower',
            'city of brass', 'mana confluence', "exiled card's colors",
        ))
        color_help = len(required & produced) + (1 if required and flexible else 0)
        amount = 0
        for item in action.get('producedMana') or []:
            try:
                amount += max(0, int(item.get('amount') or 0))
            except (AttributeError, TypeError, ValueError):
                pass
        if amount <= 0:
            amount = 1
        return (color_help, amount, str(action.get('id') or ''))

    chosen = max(actions, key=score)
    action_id = str(chosen.get('id') or '')
    if not action_id:
        return answer, canceled
    return {
        'type': 'payManaCost',
        'output': {'type': 'act', 'actionId': action_id},
    }, False


runner.choose_productive_payment_v8 = _v112_productive_kinnan_payment
'''
text += append
P.write_text(text)
print('applied arch-aware-v1.12-adversarial payment repair')
