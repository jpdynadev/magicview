#!/usr/bin/env python3
"""Add narrowly scoped v1.27 policy support for Shang-Chi + Legolas package.

This layer is inert for the F10 control because neither added card exists there.
Forge remains the rules/legality/payment authority. The patch only teaches the
Kinnan policy that Shang-Chi is a valuable creature-ability accelerator and
Legolas's Quick Reflexes is protection, avoiding an artificial candidate penalty.
"""
from pathlib import Path

P=Path(__file__).resolve().parent/'manabrew_pilot_arch_adv.py'
text=P.read_text()
if "arch-aware-v1.27-shang-legolas-adversarial" in text:
    print('v1.27 Shang/Legolas roles already applied'); raise SystemExit(0)
old="runner.PILOT_VERSION = 'arch-aware-v1.26-adversarial'"
if old not in text: raise SystemExit('expected v1.26 identity; apply v1.12-v1.26 first')
text=text.replace(old,"runner.PILOT_VERSION = 'arch-aware-v1.27-shang-legolas-adversarial'",1)
text += r'''

# v1.27 experimental role coverage; cards are absent from F10.
_V127_SHANG = 'Shang-Chi, Master of Kung Fu'
_V127_LEGOLAS = "Legolas's Quick Reflexes"
arch.ROLE_SCORES.update({_V127_SHANG: 9, _V127_LEGOLAS: 10})
arch.policy.SELF_PROTECTION.add(_V127_LEGOLAS)

_V127_ACTION_SCORE = arch.action_score

def _v127_action_score(deck: str, action: dict[str, Any], snapshot: dict[str, Any], player: int) -> int:
    score = _V127_ACTION_SCORE(deck, action, snapshot, player)
    if deck != 'Kinnan':
        return score
    name = runner._action_card(action, snapshot)
    typ = action.get('type')
    if typ == 'cast' and name == _V127_SHANG:
        # Shang-Chi is most valuable before Kinnan/Thrasios-style activated lines;
        # legality and its restricted mana remain Forge-owned.
        own_turn = snapshot.get('activePlayerId') == f'player-{player}'
        own_main = own_turn and snapshot.get('step') in {'main1','main2'}
        return max(score, 1280 if own_main else 720)
    if typ == 'cast' and name == _V127_LEGOLAS:
        # Do not fire the protection spell into an empty stack merely for value.
        # Existing target selection/Forge legality chooses the legal creature.
        if snapshot.get('stack'):
            return max(score, 2100)
        return min(score, -1200)
    return score

arch.action_score = _v127_action_score

# adversarial.composed_action_score resolves arch.action_score dynamically for Kinnan,
# so changing arch.action_score is sufficient without altering opponent policy.
'''
P.write_text(text)
print('applied arch-aware-v1.27-shang-legolas-adversarial role coverage')
