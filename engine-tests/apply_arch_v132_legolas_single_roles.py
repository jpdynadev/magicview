#!/usr/bin/env python3
"""Role coverage and pilot identity for Legolas's Quick Reflexes singleton screen."""
from pathlib import Path

path = Path('engine-tests/manabrew_pilot_arch_adv.py')
text = path.read_text()
for old in (
    "runner.PILOT_VERSION = 'arch-aware-v1.26-adversarial'",
    "runner.PILOT_VERSION = 'arch-aware-v1.11-adversarial'",
):
    text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.32-legolas-single-adversarial'")
anchor = "\nif __name__ == '__main__':\n    raise SystemExit(runner.main())\n"
block = r'''

# v1.32 singleton role coverage. Legolas's Quick Reflexes is absent from F10,
# so this addition cannot alter F10 decisions.
arch.ROLE_SCORES.update({"Legolas's Quick Reflexes": 10})
'''
if anchor not in text:
    raise SystemExit('v132 insertion anchor not found')
text = text.replace(anchor, block + anchor, 1)
path.write_text(text)
print('applied arch-aware-v1.32-legolas-single-adversarial role coverage')
