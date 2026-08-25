#!/usr/bin/env python3
"""Apply v1.19 repair for Kinnan colored-payment cancel loops.

v1.18 correctly made the initial affordability test source-aware, but the
canonical tournament forensic still reached a transient chooseAction state after
partial/reversible mana activations.  The snapshot's floating pool can include
mana associated with advertised undoMana actions, causing the pre-action guard
to believe {5}{G}{U} remains payable even though only one physical G/U source is
actually available.  The payment planner then taps that source for one color,
uses an untyped Fellwar Stone for White, cancels, and returns to the same loop.

v1.19 is deliberately narrow: when a chooseAction state contains reversible
mana (undoMana actions), do not credit transient floating colored mana toward
Kinnan's two distinct colored pips.  Require the currently advertised physical
mana sources themselves to cover G and U with distinct sources (or a source
that truly advertises capacity >=2).  This only filters Kinnan's {5}{G}{U}
activation in the transient payment-recovery state; Forge remains legality and
payment authority for every accepted action.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.19-adversarial" in text and "_v119_guard_transient_kinnan_payment" in text:
    print('v1.19 Kinnan payment-loop repair already applied')
    raise SystemExit(0)

old = "runner.PILOT_VERSION = 'arch-aware-v1.18-adversarial'"
if old not in text:
    raise SystemExit('expected v1.18 pilot identity not found; apply v1.12-v1.18 first')
text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.19-adversarial'", 1)

append = r'''

# v1.19: transient/reversible mana must not create a false colored-affordability
# positive for Kinnan's {5}{G}{U} activation.
_V118_RESPONSE_FOR_V119 = runner.base.response_for


def _v119_explicit_sources_cover_gu(inp: dict[str, Any]) -> bool:
    sources = _v118_source_color_options(inp)
    green = [(src, cap) for src, (colors, cap) in sources.items() if cap >= 1 and 'G' in colors]
    blue = [(src, cap) for src, (colors, cap) in sources.items() if cap >= 1 and 'U' in colors]
    for gsrc, gcap in green:
        for usrc, ucap in blue:
            if gsrc != usrc:
                return True
            # One physical source can only cover both pips when the advertised
            # activation itself truly produces at least two mana.
            if gcap >= 2 and ucap >= 2:
                return True
    return False


def _v119_guard_transient_kinnan_payment(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int,
    answer: dict[str, Any] | None,
) -> dict[str, Any] | None:
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
    if not chosen or chosen.get('type') != 'activateAbility':
        return answer
    if runner._action_card(chosen, snapshot) != 'Kinnan, Bonder Prodigy':
        return answer
    normalized = (str(chosen.get('cost') or '') + str(chosen.get('description') or '')).replace(' ', '').upper()
    if '{5}{G}{U}' not in normalized and '{5}{U}{G}' not in normalized:
        return answer

    actions = inp.get('actions') or []
    has_reversible_mana = any(str(a.get('type') or '') == 'undoMana' or str(a.get('id') or '').startswith('untap:') for a in actions)
    if not has_reversible_mana or _v119_explicit_sources_cover_gu(inp):
        return answer

    filtered_prompt = dict(prompt)
    filtered_input = dict(inp)
    filtered_input['actions'] = [a for a in actions if str(a.get('id') or '') != chosen_id]
    filtered_prompt['input'] = filtered_input
    retry = _V118_RESPONSE_FOR_V119(filtered_prompt, snapshot, deck, player)
    if retry is not None:
        return retry
    return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}


def _v119_response(prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int):
    answer = _V118_RESPONSE_FOR_V119(prompt, snapshot, deck, player)
    return _v119_guard_transient_kinnan_payment(prompt, snapshot, deck, player, answer)


runner.base.response_for = _v119_response
arch.base.response_for = _v119_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.19-adversarial Kinnan payment-loop repair')
