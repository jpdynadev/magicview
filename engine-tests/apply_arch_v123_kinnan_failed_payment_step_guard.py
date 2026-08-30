#!/usr/bin/env python3
"""Apply v1.23 step-scoped recurrence guard after failed Kinnan colored payment.

Canonical Logan key seat=1 seed=5010140 still loops under v1.22.  The payment
path eventually cancels Kinnan's {5}{G}{U} cost, but a later chooseAction in the
same active-player/step can immediately choose Kinnan again and recreate the
same impossible colored-payment sequence.

v1.23 records the active-player/step whenever Kinnan's payment returns cancel.
For the remainder of that exact active-player/step, Kinnan's seven-mana
activation is filtered from chooseAction.  Other legal actions remain available
and Forge remains the legality/payment authority.  The guard naturally expires
as soon as the active player or step changes, so it cannot suppress future-turn
Kinnan activations.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.23-adversarial" in text and "_v123_response" in text:
    print('v1.23 failed-payment step guard already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.22-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.22 pilot identity not found; apply v1.12-v1.22 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.23-adversarial'", 1)

append = r'''

# v1.23: after an impossible Kinnan payment, suppress immediate retries for the
# remainder of the same active-player/step.  This is a recurrence guard only.
_V122_RESPONSE = runner.base.response_for
_V123_BLOCKED_STEPS: set[tuple[int, str, str]] = set()


def _v123_step_key(snapshot: dict[str, Any], player: int) -> tuple[int, str, str]:
    return (
        int(player),
        str(snapshot.get('activePlayerId') or ''),
        str(snapshot.get('step') or ''),
    )


def _v123_is_kinnan_payment(inp: dict[str, Any]) -> bool:
    if inp.get('type') != 'payManaCost':
        return False
    if str(inp.get('cardName') or '') != 'Kinnan, Bonder Prodigy':
        return False
    cost = str(inp.get('manaCost') or '').replace(' ', '').upper()
    return '{5}{G}{U}' in cost or '{5}{U}{G}' in cost


def _v123_filter_kinnan_action(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    inp = prompt.get('input') or {}
    filtered_prompt = dict(prompt)
    filtered_input = dict(inp)
    filtered_input['actions'] = [
        a for a in (inp.get('actions') or [])
        if not _v121_is_kinnan_activation(a, snapshot)
    ]
    filtered_prompt['input'] = filtered_input
    if len(filtered_input['actions']) == len(inp.get('actions') or []):
        return _V122_RESPONSE(prompt, snapshot, deck, player)
    retry = _V122_RESPONSE(filtered_prompt, snapshot, deck, player)
    retry_out = (retry or {}).get('output') or {}
    retry_id = str(retry_out.get('actionId') or '')
    retry_action = next(
        (a for a in filtered_input['actions'] if str(a.get('id') or '') == retry_id),
        None,
    ) if retry_id else None
    if retry_action is not None and _v121_is_kinnan_activation(retry_action, snapshot):
        return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}
    return retry if retry is not None else {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}


def _v123_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    if deck != 'Kinnan':
        return _V122_RESPONSE(prompt, snapshot, deck, player)
    inp = prompt.get('input') or {}
    step_key = _v123_step_key(snapshot, player)

    if inp.get('type') == 'chooseAction' and step_key in _V123_BLOCKED_STEPS:
        return _v123_filter_kinnan_action(prompt, snapshot, deck, player)

    answer = _V122_RESPONSE(prompt, snapshot, deck, player)
    if _v123_is_kinnan_payment(inp):
        out = (answer or {}).get('output') or {}
        if out.get('type') == 'cancel':
            _V123_BLOCKED_STEPS.add(step_key)
    return answer


runner.base.response_for = _v123_response
arch.base.response_for = _v123_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.23-adversarial failed-payment step guard')
