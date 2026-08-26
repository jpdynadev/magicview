#!/usr/bin/env python3
"""Add narrowly scoped v1.28 policy support for Shang-Chi + Spellskite.

Inert for F10 because neither experimental card is present there. Forge remains
rules/legality authority; this only avoids undervaluing the new protection card.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()
if "arch-aware-v1.28-shang-spellskite-adversarial" in text:
    print('v1.28 roles already applied'); raise SystemExit(0)
old = "runner.PILOT_VERSION = 'arch-aware-v1.27-shang-legolas-adversarial'"
if old not in text:
    raise SystemExit('expected v1.27 identity; apply v1.12-v1.27 first')
text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.28-shang-spellskite-adversarial'", 1)
text += r'''

_V128_SHANG = 'Shang-Chi, Master of Kung Fu'
_V128_SPELLSKITE = 'Spellskite'
arch.ROLE_SCORES.update({_V128_SHANG: 9, _V128_SPELLSKITE: 10})

_V128_ACTION_SCORE = arch.action_score

def _v128_action_score(deck: str, action: dict[str, Any], snapshot: dict[str, Any], player: int) -> int:
    score = _V128_ACTION_SCORE(deck, action, snapshot, player)
    if deck != 'Kinnan':
        return score
    name = runner._action_card(action, snapshot)
    typ = action.get('type')
    if typ == 'cast' and name == _V128_SHANG:
        own_turn = snapshot.get('activePlayerId') == f'player-{player}'
        own_main = own_turn and snapshot.get('step') in {'main1','main2'}
        return max(score, 1280 if own_main else 720)
    if typ == 'cast' and name == _V128_SPELLSKITE:
        # Cheap persistent protection/connectivity piece; deploy proactively.
        own_turn = snapshot.get('activePlayerId') == f'player-{player}'
        own_main = own_turn and snapshot.get('step') in {'main1','main2'}
        return max(score, 1125 if own_main else 700)
    if typ == 'activateAbility' and name == _V128_SPELLSKITE:
        # Redirect only when a spell/ability is actually on the stack.
        return max(score, 2300) if snapshot.get('stack') else min(score, -1800)
    return score

arch.action_score = _v128_action_score
'''
P.write_text(text)
print('applied arch-aware-v1.28-shang-spellskite-adversarial role coverage')
