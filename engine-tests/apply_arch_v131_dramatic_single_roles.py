#!/usr/bin/env python3
"""Role coverage and pilot identity for Dramatic Reversal singleton screen."""
from pathlib import Path

path = Path('engine-tests/manabrew_pilot_arch_adv.py')
text = path.read_text()
for old in (
    "runner.PILOT_VERSION = 'arch-aware-v1.26-adversarial'",
    "runner.PILOT_VERSION = 'arch-aware-v1.11-adversarial'",
):
    text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.31-dramatic-single-adversarial'")
anchor = "\nif __name__ == '__main__':\n    raise SystemExit(runner.main())\n"
block = r'''

# v1.31 singleton role coverage. Dramatic Reversal is absent from F10,
# so this addition cannot alter F10 decisions.
arch.ROLE_SCORES.update({'Dramatic Reversal': 9})
'''
if anchor not in text:
    raise SystemExit('v131 insertion anchor not found')
text = text.replace(anchor, block + anchor, 1)
path.write_text(text)
print('applied arch-aware-v1.31-dramatic-single-adversarial role coverage')
