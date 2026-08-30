#!/usr/bin/env python3
"""Apply v1.26 failed-payment block at the combo planner boundary.

v1.25 proved the generic action scorer is not the final authority for every
Kinnan chooseAction path: the dedicated deterministic combo planner can still
select Kinnan's {5}{G}{U} activation after a failed payment in the same step.
This patch wraps runner._combo_action_response itself.  A payment-cancel latch
is bound to the current active-player/step here as well, and only Kinnan's
seven-mana activation is filtered before delegating to the existing combo
planner.  The block expires when active player or step changes.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.26-adversarial" in text and "_v126_combo_action_response" in text:
    print('v1.26 combo-path cancel block already applied')
    raise SystemExit(0)
old = "runner.PILOT_VERSION = 'arch-aware-v1.25-adversarial'"
if old not in text:
    raise SystemExit('expected v1.25 identity; apply v1.12-v1.25 first')
text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.26-adversarial'", 1)

text += r'''

# v1.26: the deterministic combo planner is a separate action-selection path.
_V126_COMBO_RESPONSE = runner._combo_action_response


def _v126_combo_action_response(
    inp: dict[str, Any],
    snapshot: dict[str, Any],
    line: str | None,
    powered_monolith: bool,
    monolith_actions: int,
):
    p = int(runner.CURRENT_KINNAN_SEAT)
    current = (str(snapshot.get('activePlayerId') or ''), str(snapshot.get('step') or ''))

    # Consume the payment failure at this final Kinnan-specific planner too.
    if p in _V124_FAILED_PAYMENT_LATCH:
        _V124_FAILED_PAYMENT_LATCH.discard(p)
        _V124_BLOCKED_STEP[p] = current
    blocked = _V124_BLOCKED_STEP.get(p)
    if blocked is not None and blocked != current:
        _V124_BLOCKED_STEP.pop(p, None)
        blocked = None

    patched = inp
    if blocked == current:
        patched = dict(inp)
        patched['actions'] = [
            a for a in (inp.get('actions') or [])
            if not _v121_is_kinnan_activation(a, snapshot)
        ]
    return _V126_COMBO_RESPONSE(
        patched, snapshot, line, powered_monolith, monolith_actions
    )


runner._combo_action_response = _v126_combo_action_response
'''
P.write_text(text)
print('applied arch-aware-v1.26-adversarial combo-path cancel block')
