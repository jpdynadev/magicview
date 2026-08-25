#!/usr/bin/env python3
"""Apply v1.24 payment-cancel latch at the actual payment-policy layer.

v1.23 tried to observe payManaCost cancellation through response_for, but the
architecture pilot dispatches mana payment through runner.choose_productive_payment_v8.
The canonical Logan key therefore continued to retry Kinnan after cancellation.

v1.24 wraps the actual payment function.  If Kinnan's {5}{G}{U} payment returns
cancel, a per-player latch is set.  On the next Kinnan chooseAction prompt we bind
that latch to the current active-player/step and filter Kinnan's seven-mana
activation for the remainder of that step.  The latch naturally expires when
active player or step changes.  No Forge legality or payment semantics are
invented; this only prevents deterministic re-entry into a payment path that the
pilot itself just proved it could not complete.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.24-adversarial" in text and "_V124_FAILED_PAYMENT_LATCH" in text:
    print('v1.24 payment cancel latch already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.23-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.23 pilot identity not found; apply v1.12-v1.23 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.24-adversarial'", 1)

append = r'''

# v1.24: observe cancellation at the actual payment-policy layer, not response_for.
_V123_RESPONSE = runner.base.response_for
_V123_PAYMENT = runner.choose_productive_payment_v8
_V124_FAILED_PAYMENT_LATCH: set[int] = set()
_V124_BLOCKED_STEP: dict[int, tuple[str, str]] = {}


def _v124_is_kinnan_cost(inp: dict[str, Any]) -> bool:
    if inp.get('type') != 'payManaCost':
        return False
    if str(inp.get('cardName') or '') != 'Kinnan, Bonder Prodigy':
        return False
    cost = str(inp.get('manaCost') or '').replace(' ', '').upper()
    return '{5}{G}{U}' in cost or '{5}{U}{G}' in cost


def _v124_payment(inp: dict[str, Any], player: int):
    answer, canceled = _V123_PAYMENT(inp, player)
    out = (answer or {}).get('output') or {}
    if _v124_is_kinnan_cost(inp) and (canceled or out.get('type') == 'cancel'):
        _V124_FAILED_PAYMENT_LATCH.add(int(player))
    return answer, canceled


runner.choose_productive_payment_v8 = _v124_payment


def _v124_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    if deck != 'Kinnan':
        return _V123_RESPONSE(prompt, snapshot, deck, player)
    inp = prompt.get('input') or {}
    p = int(player)
    current = (str(snapshot.get('activePlayerId') or ''), str(snapshot.get('step') or ''))

    # Bind a freshly observed payment failure to the first subsequent decision
    # state.  This is guaranteed to run after choose_productive_payment_v8 set
    # the latch, regardless of response_for wrapper ordering.
    if p in _V124_FAILED_PAYMENT_LATCH:
        _V124_FAILED_PAYMENT_LATCH.discard(p)
        _V124_BLOCKED_STEP[p] = current

    blocked = _V124_BLOCKED_STEP.get(p)
    if blocked is not None and blocked != current:
        _V124_BLOCKED_STEP.pop(p, None)
        blocked = None

    if inp.get('type') == 'chooseAction' and blocked == current:
        patched = dict(prompt)
        pinp = dict(inp)
        pinp['actions'] = [
            a for a in (inp.get('actions') or [])
            if not _v121_is_kinnan_activation(a, snapshot)
        ]
        patched['input'] = pinp
        answer = _V123_RESPONSE(patched, snapshot, deck, player)
        out = (answer or {}).get('output') or {}
        aid = str(out.get('actionId') or '')
        chosen = next((a for a in pinp['actions'] if str(a.get('id') or '') == aid), None) if aid else None
        if chosen is not None and _v121_is_kinnan_activation(chosen, snapshot):
            return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}
        return answer if answer is not None else {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}

    return _V123_RESPONSE(prompt, snapshot, deck, player)


runner.base.response_for = _v124_response
arch.base.response_for = _v124_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.24-adversarial payment cancel latch')
