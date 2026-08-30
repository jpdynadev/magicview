#!/usr/bin/env python3
"""Apply v1.24 no-progress recurrence guard for Kinnan {5}{G}{U} payments.

v1.23 still reproduces the Logan seat=1 seed=5010140 idle loop.  The trace
shows that after a Kinnan payment attempt cancels, transient/stale floating mana
can make the next attempt look color-feasible even though the underlying hand +
battlefield position has not gained a new source.  The pilot then repeats the
same activate -> partial payment -> cancel cycle.

v1.24 does not guess Forge legality.  It records the strategic position whenever
an attempted Kinnan payment actually returns `cancel`.  If the pilot tries the
same seven-mana Kinnan activation again with the same hand, battlefield, active
player and step, that activation is filtered once and the existing policy picks
another legal action (or passes).  A draw, permanent change, turn/step change,
or other meaningful position change automatically permits a fresh attempt.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.24-adversarial" in text and "_v124_payment_recurrence_response" in text:
    print('v1.24 Kinnan payment recurrence guard already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.23-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.23 pilot identity not found; apply v1.12-v1.23 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.24-adversarial'", 1)

append = r'''

# v1.24: prevent exact strategic recurrence after a real Kinnan payment cancel.
_V123_RESPONSE = runner.base.response_for
_V124_BLOCKED_KINNAN_POSITIONS: set[tuple[Any, ...]] = set()


def _v124_position_key(snapshot: dict[str, Any], player: int) -> tuple[Any, ...]:
    def names(zone: str) -> tuple[str, ...]:
        try:
            cards = runner.base.zone_cards(snapshot, player, zone) or []
            return tuple(sorted(runner.base.card_name(card) for card in cards))
        except Exception:
            return ()
    return (
        player,
        str(snapshot.get('activePlayerId') or ''),
        str(snapshot.get('step') or ''),
        str(snapshot.get('phase') or ''),
        names('hand'),
        names('battlefield'),
    )


def _v124_is_kinnan_seven_action(action: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    if action.get('type') != 'activateAbility':
        return False
    try:
        if runner._action_card(action, snapshot) != 'Kinnan, Bonder Prodigy':
            return False
    except Exception:
        return False
    raw = (str(action.get('cost') or '') + str(action.get('description') or '')).replace(' ', '').upper()
    return '{5}{G}{U}' in raw or '{5}{U}{G}' in raw


def _v124_payment_recurrence_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    inp = prompt.get('input') or {}
    key = _v124_position_key(snapshot, player)

    # If this unchanged strategic position already produced a genuine payment
    # cancellation, do not enter the identical Kinnan payment branch again.
    if deck == 'Kinnan' and inp.get('type') == 'chooseAction' and key in _V124_BLOCKED_KINNAN_POSITIONS:
        answer = _V123_RESPONSE(prompt, snapshot, deck, player)
        output = (answer or {}).get('output') or {}
        chosen_id = str(output.get('actionId') or '')
        chosen = next((a for a in (inp.get('actions') or []) if str(a.get('id') or '') == chosen_id), None)
        if chosen and _v124_is_kinnan_seven_action(chosen, snapshot):
            patched_prompt = dict(prompt)
            patched_input = dict(inp)
            patched_input['actions'] = [a for a in (inp.get('actions') or []) if not _v124_is_kinnan_seven_action(a, snapshot)]
            patched_prompt['input'] = patched_input
            retry = _V123_RESPONSE(patched_prompt, snapshot, deck, player)
            if retry is not None:
                return retry
            return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}
        return answer

    answer = _V123_RESPONSE(prompt, snapshot, deck, player)
    if deck == 'Kinnan' and inp.get('type') == 'payManaCost':
        card_name = str(inp.get('cardName') or '')
        cost = str(inp.get('manaCost') or '').replace(' ', '').upper()
        output = (answer or {}).get('output') or {}
        if (
            card_name == 'Kinnan, Bonder Prodigy'
            and ('{5}{G}{U}' in cost or '{5}{U}{G}' in cost)
            and output.get('type') == 'cancel'
        ):
            _V124_BLOCKED_KINNAN_POSITIONS.add(key)
    return answer


runner.base.response_for = _v124_payment_recurrence_response
arch.base.response_for = _v124_payment_recurrence_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.24-adversarial Kinnan payment recurrence guard')
