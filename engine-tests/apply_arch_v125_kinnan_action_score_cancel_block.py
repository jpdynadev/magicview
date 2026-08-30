#!/usr/bin/env python3
"""Apply v1.25 failed-payment block at Kinnan action scoring.

v1.24 correctly observes a failed Kinnan {5}{G}{U} payment, but the canonical
Logan forensic proves some later chooseAction decisions bypass the response_for
filtering layer.  The action scorer is the common path used to rank advertised
Kinnan actions, so v1.25 binds the existing payment-failure latch there and
makes only Kinnan's seven-mana activation noncompetitive for the remainder of
the same active-player/step.  The block expires on step change. Forge remains
legality/payment authority; all other actions retain their existing scores.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.25-adversarial" in text and "_v125_action_score" in text:
    print('v1.25 action-score cancel block already applied')
    raise SystemExit(0)
old = "runner.PILOT_VERSION = 'arch-aware-v1.24-adversarial'"
if old not in text:
    raise SystemExit('expected v1.24 identity; apply v1.12-v1.24 first')
text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.25-adversarial'", 1)

text += r'''

# v1.25: enforce the failed-payment block at the common action-scoring layer.
_V125_ACTION_SCORE = arch.base.action_score


def _v125_action_score(deck: str, action: dict[str, Any], snapshot: dict[str, Any], player: int) -> int:
    if deck == 'Kinnan':
        p = int(player)
        current = (str(snapshot.get('activePlayerId') or ''), str(snapshot.get('step') or ''))
        # Payment layer can set this even when a later response_for wrapper is
        # bypassed. Bind it on the next action-scoring pass.
        if p in _V124_FAILED_PAYMENT_LATCH:
            _V124_FAILED_PAYMENT_LATCH.discard(p)
            _V124_BLOCKED_STEP[p] = current
        blocked = _V124_BLOCKED_STEP.get(p)
        if blocked is not None and blocked != current:
            _V124_BLOCKED_STEP.pop(p, None)
            blocked = None
        if blocked == current and _v121_is_kinnan_activation(action, snapshot):
            return -1000000
    return _V125_ACTION_SCORE(deck, action, snapshot, player)


arch.base.action_score = _v125_action_score
runner.base.action_score = _v125_action_score
'''
P.write_text(text)
print('applied arch-aware-v1.25-adversarial action-score cancel block')
