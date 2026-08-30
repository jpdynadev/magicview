#!/usr/bin/env python3
"""Apply v1.40 Monolith affordability guard at the combo-planner boundary.

The v1.39 forensic replay of canonical key seed 6930008 / seat 3 / balanced
showed the dedicated deterministic combo planner bypassing the existing v1.14
response-layer Monolith affordability guard.  The planner selected Grim
Monolith's {4}: untap activation while the authoritative chooseAction prompt
advertised only Ancient Tomb ({C}{C}) and Elvish Spirit Guide ({G}) as external
mana sources.  The subsequent payment could not reach four mana, cancelled,
and the same no-progress family repeated before a later payment path idled.

This repair is intentionally narrow: filter only Basalt/Grim Monolith untap
activations at the final combo-planner boundary when floating mana plus OTHER
advertised mana sources cannot meet the printed untap cost.  Forge remains the
legality/payment authority and all other actions are unchanged.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.40-adversarial" in text and "_v140_combo_monolith_affordability" in text:
    print('v1.40 combo Monolith affordability guard already applied')
    raise SystemExit(0)
old = "runner.PILOT_VERSION = 'arch-aware-v1.28-shang-spellskite-adversarial'"
if old not in text:
    raise SystemExit('expected v1.28 pilot identity; apply v1.12-v1.28 first')
text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.40-adversarial'", 1)

text += r'''

# v1.40: v1.14 guarded the response_for path, but the deterministic combo
# planner is a separate final action-selection path.  Enforce the same narrow
# Monolith affordability invariant immediately before that planner chooses.
_V140_COMBO_RESPONSE = runner._combo_action_response


def _v140_monolith_unpayable(action: dict[str, Any], inp: dict[str, Any], snapshot: dict[str, Any], player: int) -> bool:
    if action.get('type') != 'activateAbility':
        return False
    card = runner._action_card(action, snapshot)
    if card not in {'Basalt Monolith', 'Grim Monolith'}:
        return False
    description = str(action.get('description') or action.get('label') or '')
    if 'untap' not in description.lower():
        return False
    normalized_cost = str(action.get('cost') or '').replace(' ', '').upper()
    required = {'{3}': 3, '{4}': 4}.get(normalized_cost)
    if required is None:
        return False
    source_id = str(action.get('cardId') or action.get('card_id') or '')
    if not source_id:
        return False
    return _v114_external_mana_upper_bound(inp, snapshot, player, source_id) < required


def _v140_combo_monolith_affordability(
    inp: dict[str, Any], snapshot: dict[str, Any], line: str | None,
    powered_monolith: bool, monolith_actions: int,
):
    p = int(runner.CURRENT_KINNAN_SEAT)
    actions = list(inp.get('actions') or [])
    filtered = [a for a in actions if not _v140_monolith_unpayable(a, inp, snapshot, p)]
    patched = inp
    if len(filtered) != len(actions):
        patched = dict(inp)
        patched['actions'] = filtered
    return _V140_COMBO_RESPONSE(patched, snapshot, line, powered_monolith, monolith_actions)


runner._combo_action_response = _v140_combo_monolith_affordability
'''
P.write_text(text)
print('applied arch-aware-v1.40-adversarial combo Monolith affordability guard')
