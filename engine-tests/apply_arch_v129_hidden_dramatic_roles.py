#!/usr/bin/env python3
"""Role coverage and pilot identity for Hidden Strings + Dramatic Reversal screen.

This patch is intentionally narrow: it preserves the validated v1.26 execution
repairs and only adds explicit Kinnan scoring/identity for the two experimental
cards. F10 does not contain either card, so its policy is unchanged.
"""
from pathlib import Path

path = Path('engine-tests/manabrew_pilot_arch_adv.py')
text = path.read_text()
for old in (
    "runner.PILOT_VERSION = 'arch-aware-v1.26-adversarial'",
    "runner.PILOT_VERSION = 'arch-aware-v1.11-adversarial'",
):
    text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.29-hidden-dramatic-adversarial'")
anchor = "\nif __name__ == '__main__':\n    raise SystemExit(runner.main())\n"
block = r'''

# v1.29 experimental role coverage. Hidden Strings and Dramatic Reversal are
# absent from the F10 control, so these additions cannot alter F10 decisions.
arch.ROLE_SCORES.update({
    'Hidden Strings': 9,
    'Dramatic Reversal': 9,
})
'''
if anchor not in text:
    raise SystemExit('v129 insertion anchor not found')
text = text.replace(anchor, block + anchor, 1)
path.write_text(text)
print('applied arch-aware-v1.29-hidden-dramatic-adversarial role coverage')
