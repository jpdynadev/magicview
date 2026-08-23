#!/usr/bin/env python3
"""Apply v1.15 payment-progress repair for Monolith untap activations.

The v1.14 canonical F10 replay for seed 3520304 showed that the pre-action
Monolith affordability guard was not sufficient. Forge's authoritative
payManaCost prompt for Basalt Monolith's {3}: untap activation still advertised
an external legal mana action (Sol Ring), while the legacy payment chooser
returned cancel. That returned the game to the same untap action and recreated
the no-progress loop.

v1.15 is deliberately narrow. If the existing payment chooser is about to
cancel a Basalt Monolith {3} or Grim Monolith {4} untap payment while Forge is
still advertising zero-mana-cost *external* mana abilities, consume one such
Forge-advertised source first. The Monolith being untapped is explicitly
excluded from financing its own untap. Forge remains the legality/payment
authority; when no productive external source remains, the original cancel is
preserved.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.15-adversarial" in text and "_v115_productive_monolith_payment" in text:
    print('v1.15 monolith payment-progress repair already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.14-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.14 pilot identity not found; apply v1.12-v1.14 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.15-adversarial'", 1)

append = r'''

# v1.15: if the legacy payment policy wants to cancel a Monolith untap payment
# while Forge still advertises an external zero-mana-input mana ability, use one
# such authoritative payment action first. The Monolith being untapped is never
# allowed to finance its own untap here.
_V114_PAYMENT = runner.choose_productive_payment_v8


def _v115_productive_monolith_payment(inp: dict[str, Any], player: int):
    answer, canceled = _V114_PAYMENT(inp, player)
    if not canceled:
        return answer, canceled

    card_name = str(inp.get('cardName') or '')
    normalized = str(inp.get('manaCost') or '').replace(' ', '').upper()
    required = {'Basalt Monolith': '{3}', 'Grim Monolith': '{4}'}.get(card_name)
    if required is None or normalized != required:
        return answer, canceled

    payment_card_id = str(inp.get('cardId') or inp.get('card_id') or '')
    candidates = []
    for action in inp.get('actions', []) or []:
        if action.get('type') != 'activateManaAbility' or not action.get('isManaAbility'):
            continue
        source_id = str(action.get('cardId') or action.get('card_id') or '')
        if payment_card_id and source_id == payment_card_id:
            continue
        cost = str(action.get('cost') or '').replace(' ', '').upper()
        # Preserve the v1.12 safety rule: only consume Forge-advertised mana
        # actions that require no additional mana payment. Tap/life/sacrifice
        # costs remain engine-owned and are already represented as legal actions.
        if any(token in cost for token in (
            '{0}', '{1}', '{2}', '{3}', '{4}', '{5}',
            '{W}', '{U}', '{B}', '{R}', '{G}', '{C}', '{X}',
        )):
            continue
        action_id = str(action.get('id') or '')
        if not action_id:
            continue
        amount = 0
        for item in action.get('producedMana') or []:
            try:
                amount += max(0, int(item.get('amount') or 0))
            except (AttributeError, TypeError, ValueError):
                pass
        if amount <= 0:
            amount = 1
        candidates.append((amount, action_id, action))

    if not candidates:
        return answer, canceled

    _, action_id, _ = max(candidates, key=lambda item: (item[0], item[1]))
    return {
        'type': 'payManaCost',
        'output': {'type': 'act', 'actionId': action_id},
    }, False


runner.choose_productive_payment_v8 = _v115_productive_monolith_payment
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.15-adversarial monolith payment-progress repair')
