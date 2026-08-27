#!/usr/bin/env python3
"""Role coverage and pilot identity for Power Artifact + Muddle package screen."""
from pathlib import Path

path = Path('engine-tests/manabrew_pilot_arch_adv.py')
text = path.read_text()
for old in (
    "runner.PILOT_VERSION = 'arch-aware-v1.26-adversarial'",
    "runner.PILOT_VERSION = 'arch-aware-v1.11-adversarial'",
):
    text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.33-power-muddle-adversarial'")
anchor = "\nif __name__ == '__main__':\n    raise SystemExit(runner.main())\n"
block = r'''

# v1.33 challenger-only role coverage. These cards are absent from F10, so
# this addition cannot alter baseline card-role decisions.
arch.ROLE_SCORES.update({
    "Power Artifact": 10,
    "Muddle the Mixture": 9,
})
'''
if anchor not in text:
    raise SystemExit('v133 insertion anchor not found')
text = text.replace(anchor, block + anchor, 1)
path.write_text(text)
print('applied arch-aware-v1.33-power-muddle-adversarial role coverage')
