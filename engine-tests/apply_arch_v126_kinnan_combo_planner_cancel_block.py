#!/usr/bin/env python3
"""Apply v1.26 failed-payment block inside the deterministic combo planner.

v1.25 bound the Kinnan payment-cancel latch at action scoring, but the canonical
Logan key proved the deterministic combo planner can select Kinnan's seven-mana
activation directly, bypassing that scoring path.  v1.26 binds the same latch at
runner._combo_action_response and removes only Kinnan's {5}{G}{U} activation for
the remainder of the same active-player/step after the pilot has already failed
that payment.  The block expires on step/active-player change.  Forge remains
the legality/payment authority and every other combo action is unchanged.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.26-adversarial" in text and "_v126_combo_action_response" in text:
    print('v1.26 combo-planner cancel block already applied')
    raise SystemExit(0)
old = "runner.PILOT_VERSION = 'arch-aware-v1.25-adversarial'"
if old not in text:
    raise SystemExit('expected v1.25 identity; apply v1.12-v1.25 first')
text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.26-adversarial'", 1)

text += r'''

# v1.26: deterministic combo planner must honor the same failed-payment latch.
_V126_COMBO_ACTION_RESPONSE = runner._combo_action_response


def _v126_combo_action_response(
    inp: dict[str, Any],
    snapshot: dict[str, Any],
    line: str | None,
    powered_monolith: bool,
    monolith_actions: int,
):
    p = int(getattr(runner, 'CURRENT_KINNAN_SEAT', 0))
    current = (str(snapshot.get('activePlayerId') or ''), str(snapshot.get('step') or ''))

    # Payment cancellation is observed by v1.24 at the actual payment-policy
    # layer.  Bind it here because combo selection can bypass response_for and
    # action_score entirely.
    if p in _V124_FAILED_PAYMENT_LATCH:
        _V124_FAILED_PAYMENT_LATCH.discard(p)
        _V124_BLOCKED_STEP[p] = current

    blocked = _V124_BLOCKED_STEP.get(p)
    if blocked is not None and blocked != current:
        _V124_BLOCKED_STEP.pop(p, None)
        blocked = None

    if blocked == current:
        patched = dict(inp)
        patched['actions'] = [
            action for action in (inp.get('actions') or [])
            if not _v121_is_kinnan_activation(action, snapshot)
        ]
        return _V126_COMBO_ACTION_RESPONSE(
            patched, snapshot, line, powered_monolith, monolith_actions
        )

    return _V126_COMBO_ACTION_RESPONSE(
        inp, snapshot, line, powered_monolith, monolith_actions
    )


runner._combo_action_response = _v126_combo_action_response
'''
P.write_text(text)
print('applied arch-aware-v1.26-adversarial combo-planner cancel block')
