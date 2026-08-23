#!/usr/bin/env python3
"""Apply v1.14 affordability repair for Monolith untap activations.

The v1.13 F10 forensic for seed 3520304 showed a deterministic no-progress loop:
the pilot repeatedly selected Basalt Monolith's {3}: untap activation even though
Forge's authoritative payment prompt could not complete that payment. The payment
was cancelled and the same activation was immediately selected again until idle
 timeout.

v1.14 is deliberately narrow. Before accepting Basalt Monolith or Grim Monolith's
mana-costed untap activation, it computes an optimistic payment bound from the
floating mana pool plus *other* currently advertised mana sources. The Monolith
being untapped is excluded from financing its own untap cost. If that external
bound cannot pay the cost, the action is filtered and the existing v1.13 policy
chooses another legal action. Forge remains the legality/payment authority.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.14-adversarial" in text and "_v114_guard_monolith_untap" in text:
    print('v1.14 monolith affordability repair already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.13-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.13 pilot identity not found; apply v1.12 and v1.13 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.14-adversarial'", 1)

append = r'''

# v1.14: avoid activate-then-cancel loops for Monolith untap abilities when the
# only apparent mana capacity includes the tapped Monolith itself. A permanent
# being untapped cannot productively finance its own untap payment in this path.
_V113_RESPONSE = runner.base.response_for


def _v114_external_mana_upper_bound(
    inp: dict[str, Any], snapshot: dict[str, Any], player: int, excluded_card_id: str
) -> int:
    per_source: dict[str, int] = {}
    for action in inp.get('actions', []) or []:
        source = str(action.get('cardId') or action.get('card_id') or '')
        if not source or source == excluded_card_id:
            continue
        capacity = _mana_action_capacity(action)
        if capacity <= 0:
            continue
        per_source[source] = max(per_source.get(source, 0), capacity)
    return _player_mana_pool_total(snapshot, player) + sum(per_source.values())


def _v114_guard_monolith_untap(
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
    chosen = next(
        (action for action in (inp.get('actions') or []) if str(action.get('id') or '') == chosen_id),
        None,
    )
    if not chosen or chosen.get('type') != 'activateAbility':
        return answer
    card = runner._action_card(chosen, snapshot)
    if card not in {'Basalt Monolith', 'Grim Monolith'}:
        return answer
    description = str(chosen.get('description') or chosen.get('label') or '')
    if 'untap' not in description.lower():
        return answer
    normalized_cost = str(chosen.get('cost') or '').replace(' ', '').upper()
    required = {'{3}': 3, '{4}': 4}.get(normalized_cost)
    if required is None:
        return answer
    chosen_card_id = str(chosen.get('cardId') or chosen.get('card_id') or '')
    if not chosen_card_id:
        return answer
    if _v114_external_mana_upper_bound(inp, snapshot, player, chosen_card_id) >= required:
        return answer

    filtered_prompt = dict(prompt)
    filtered_input = dict(inp)
    filtered_input['actions'] = [
        action for action in (inp.get('actions') or [])
        if str(action.get('id') or '') != chosen_id
    ]
    filtered_prompt['input'] = filtered_input
    retry = _V113_RESPONSE(filtered_prompt, snapshot, deck, player)
    if retry is not None:
        return retry
    return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}


def _v114_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    answer = _V113_RESPONSE(prompt, snapshot, deck, player)
    return _v114_guard_monolith_untap(prompt, snapshot, deck, player, answer)


runner.base.response_for = _v114_response
arch.base.response_for = _v114_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.14-adversarial monolith affordability repair')
