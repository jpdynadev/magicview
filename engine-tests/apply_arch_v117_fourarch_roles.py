#!/usr/bin/env python3
"""Add fair role coverage for the four-architecture telemetry experiment.

The experiment deliberately includes cards not present in F10.  Without this
layer the existing mulligan/action heuristics would fail to count several added
mana creatures as mana sources and would undervalue tournament/node cards.  The
changes are inert for F10 because they only add classifications for cards F10
does not contain.  Bump pilot identity so no v1.16 row can be mixed in.
"""
from pathlib import Path

path = Path('engine-tests/manabrew_pilot_arch_adv.py')
text = path.read_text()
text = text.replace("runner.PILOT_VERSION = 'arch-aware-v1.16-adversarial'", "runner.PILOT_VERSION = 'arch-aware-v1.17-fourarch-adversarial'")
text = text.replace("runner.PILOT_VERSION = 'arch-aware-v1.11-adversarial'", "runner.PILOT_VERSION = 'arch-aware-v1.17-fourarch-adversarial'")
anchor = "\nif __name__ == '__main__':\n    raise SystemExit(runner.main())\n"
block = r'''

# Four-architecture experimental role coverage.  These names are absent from
# the F10 control, so extending their classification cannot change F10 policy.
base.LANDS.update({'Exotic Orchard', 'Tarnished Citadel'})
runner.ONE_G_DORKS.update({
    'Arbor Elf', 'Boreal Druid', 'Paradise Druid', 'Incubation Druid',
    'Priest of Titania', "Kiora's Follower", 'Devoted Druid', 'Wall of Roots',
    'Elvish Archdruid', 'Gyre Engineer',
})
arch.ROLE_SCORES.update({
    'Arbor Elf': 7, 'Boreal Druid': 7, 'Paradise Druid': 7,
    'Incubation Druid': 8, 'Priest of Titania': 8, "Kiora's Follower": 8,
    'Wall of Roots': 8, 'Elvish Archdruid': 7, 'Gyre Engineer': 7,
    'Rings of Brighthearth': 8, 'Freed from the Real': 9, "Pemmin's Aura": 9,
    'Training Grounds': 8, "Biomancer's Familiar": 8,
    'Flash Photography': 9, 'Hidden Strings': 8, 'Step Through': 8,
    'Dizzy Spell': 8, 'Dramatic Reversal': 8, 'Twincast': 7,
    'Sudden Substitution': 8, 'Commandeer': 8, 'Disrupting Shoal': 8,
    'Snapback': 7, 'Imposter Mech': 8, 'Counterbalance': 8,
    'Wan Shi Tong, Librarian': 8, 'The Cabbage Merchant': 8,
    'High Fae Trickster': 8, 'Consecrated Sphinx': 8,
    'Colossal Skyturtle': 7, 'Hullbreaker Horror': 9, 'The One Ring': 9,
})
'''
if anchor not in text:
    raise SystemExit('fourarch role insertion anchor not found')
text = text.replace(anchor, block + anchor, 1)
path.write_text(text)
print('applied arch-aware-v1.17-fourarch-adversarial role coverage')
