#!/usr/bin/env python3
"""Apply v1.22 conservative colored-reserve guard for Kinnan's {5}{G}{U} activation.

v1.21 still allows the canonical Logan seat=1 seed=5010140 loop when one
required color is already floating.  The outer guard then asks only for the
other color, but Forge's subsequent generic payment can consume the floating
colored mana before the colored requirement is satisfied.  With Waterlogged
Grove as the only explicit G/U physical source and Fellwar Stone advertising no
producedMana, payment later strands on the other colored pip and repeats.

v1.22 is deliberately conservative: unless both G and U are already floating,
Kinnan's activation requires two distinct *explicit* physical sources whose
advertised producedMana can cover G and U.  Untyped mana abilities are never
invented as colored backup.  This can decline a marginally legal activation,
but it cannot create an illegal colored-payment path; Forge remains the rules
and payment authority.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.22-adversarial" in text and "_v122_outer_response" in text:
    print('v1.22 conservative Kinnan color-reserve guard already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.21-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.21 pilot identity not found; apply v1.12-v1.21 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.22-adversarial'", 1)

append = r'''

# v1.22: reserve colored requirements against generic-payment consumption.
_V121_RESPONSE = runner.base.response_for


def _v122_has_safe_colored_reserve(snapshot: dict[str, Any], inp: dict[str, Any], player: int) -> bool:
    floating = _v118_floating_mana(snapshot, player)
    if floating.get('G', 0) >= 1 and floating.get('U', 0) >= 1:
        return True

    # If either colored requirement is not already secured in the pool, require
    # explicit physical backup for *both* colors.  This protects against Forge
    # consuming a currently-floating colored mana toward the generic five.
    sources = _v121_explicit_sources(inp)
    green = [src for src, colors in sources.items() if 'G' in colors]
    blue = [src for src, colors in sources.items() if 'U' in colors]
    return any(gsrc != usrc for gsrc in green for usrc in blue)


def _v122_outer_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    answer = _V121_RESPONSE(prompt, snapshot, deck, player)
    if deck != 'Kinnan':
        return answer
    inp = prompt.get('input') or {}
    if inp.get('type') != 'chooseAction':
        return answer
    output = (answer or {}).get('output') or {}
    if output.get('type') != 'act' or not output.get('actionId'):
        return answer

    chosen_id = str(output['actionId'])
    chosen = next((a for a in (inp.get('actions') or []) if str(a.get('id') or '') == chosen_id), None)
    if not _v121_is_kinnan_activation(chosen, snapshot):
        return answer
    if _v122_has_safe_colored_reserve(snapshot, inp, player):
        return answer

    filtered_prompt = dict(prompt)
    filtered_input = dict(inp)
    filtered_input['actions'] = [a for a in (inp.get('actions') or []) if str(a.get('id') or '') != chosen_id]
    filtered_prompt['input'] = filtered_input
    retry = _V121_RESPONSE(filtered_prompt, snapshot, deck, player)
    retry_output = (retry or {}).get('output') or {}
    retry_id = str(retry_output.get('actionId') or '')
    retry_action = next((a for a in filtered_input['actions'] if str(a.get('id') or '') == retry_id), None) if retry_id else None
    if retry_action is not None and _v121_is_kinnan_activation(retry_action, snapshot):
        return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}
    return retry if retry is not None else {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}


runner.base.response_for = _v122_outer_response
arch.base.response_for = _v122_outer_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.22-adversarial conservative Kinnan color-reserve guard')
