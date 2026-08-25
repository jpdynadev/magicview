#!/usr/bin/env python3
"""Apply v1.21 outer colored-source guard for Kinnan's {5}{G}{U} activation.

v1.20 still reproduced the canonical Logan seat=1 seed=5010140 idle loop.  The
trace proves that a Kinnan activation can escape the earlier nested affordability
wrapper, enter payment with only one physical G/U source (Waterlogged Grove),
spend that source on one color, then discover Fellwar Stone only offers White,
cancel, and retry.

v1.21 installs one final outer chooseAction guard *after* all v1.12-v1.20
wrappers.  It independently checks physical source identity for the missing G/U
pips using only explicit producedMana.  Multiple G/U choices from one permanent
remain alternatives, never two sources; mana abilities without producedMana are
not invented as colored sources.  If the exact chosen action is Kinnan and the
colored assignment is impossible, it is removed and the pre-v1.21 policy is
asked to choose another legal action.  Forge remains legality/payment authority.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.21-adversarial" in text and "_v121_outer_response" in text:
    print('v1.21 outer Kinnan affordability guard already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.20-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.20 pilot identity not found; apply v1.12-v1.20 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.21-adversarial'", 1)

append = r'''

# v1.21: final outer guard so no later wrapper can bypass physical G/U source
# assignment for Kinnan's seven-mana activation.
_V120_RESPONSE = runner.base.response_for


def _v121_explicit_sources(inp: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for action in inp.get('actions', []) or []:
        if not (action.get('isManaAbility') or action.get('type') == 'activateManaAbility'):
            continue
        source = str(action.get('cardId') or action.get('card_id') or '')
        if not source:
            continue
        for item in action.get('producedMana') or []:
            try:
                amount = max(0, int((item or {}).get('amount') or 0))
            except (AttributeError, TypeError, ValueError):
                amount = 0
            if amount <= 0:
                continue
            color = _v118_color_token((item or {}).get('color'))
            if color in {'G', 'U'}:
                out.setdefault(source, set()).add(color)
    return out


def _v121_has_colored_assignment(snapshot: dict[str, Any], inp: dict[str, Any], player: int) -> bool:
    floating = _v118_floating_mana(snapshot, player)
    need_g = floating.get('G', 0) < 1
    need_u = floating.get('U', 0) < 1
    if not need_g and not need_u:
        return True

    sources = _v121_explicit_sources(inp)
    if need_g and not need_u:
        return any('G' in colors for colors in sources.values())
    if need_u and not need_g:
        return any('U' in colors for colors in sources.values())

    green = [src for src, colors in sources.items() if 'G' in colors]
    blue = [src for src, colors in sources.items() if 'U' in colors]
    return any(gsrc != usrc for gsrc in green for usrc in blue)


def _v121_is_kinnan_activation(action: dict[str, Any] | None, snapshot: dict[str, Any]) -> bool:
    if not action or action.get('type') != 'activateAbility':
        return False
    if runner._action_card(action, snapshot) != 'Kinnan, Bonder Prodigy':
        return False
    normalized = (str(action.get('cost') or '') + str(action.get('description') or '')).replace(' ', '').upper()
    return '{5}{G}{U}' in normalized or '{5}{U}{G}' in normalized


def _v121_outer_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    answer = _V120_RESPONSE(prompt, snapshot, deck, player)
    if deck != 'Kinnan':
        return answer
    inp = prompt.get('input') or {}
    if inp.get('type') != 'chooseAction':
        return answer
    output = (answer or {}).get('output') or {}
    if output.get('type') != 'act' or not output.get('actionId'):
        return answer

    chosen_id = str(output['actionId'])
    chosen = next(
        (a for a in (inp.get('actions') or []) if str(a.get('id') or '') == chosen_id),
        None,
    )
    if not _v121_is_kinnan_activation(chosen, snapshot):
        return answer
    if _v121_has_colored_assignment(snapshot, inp, player):
        return answer

    filtered_prompt = dict(prompt)
    filtered_input = dict(inp)
    filtered_input['actions'] = [
        a for a in (inp.get('actions') or [])
        if str(a.get('id') or '') != chosen_id
    ]
    filtered_prompt['input'] = filtered_input
    retry = _V120_RESPONSE(filtered_prompt, snapshot, deck, player)
    retry_output = (retry or {}).get('output') or {}
    retry_id = str(retry_output.get('actionId') or '')
    retry_action = next(
        (a for a in filtered_input['actions'] if str(a.get('id') or '') == retry_id),
        None,
    ) if retry_id else None
    if retry_action is not None and _v121_is_kinnan_activation(retry_action, snapshot):
        return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}
    if retry is not None:
        return retry
    return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}


runner.base.response_for = _v121_outer_response
arch.base.response_for = _v121_outer_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.21-adversarial outer Kinnan affordability guard')
