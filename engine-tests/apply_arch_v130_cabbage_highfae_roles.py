#!/usr/bin/env python3
"""Assign a fresh identity for the Cabbage Merchant + High Fae package screen.

Role coverage for both cards is already installed by v1.17 four-architecture
roles. This patch only advances the pilot identity so no rows from other
experimental profiles can be mixed into this comparison.
"""
from pathlib import Path

path = Path('engine-tests/manabrew_pilot_arch_adv.py')
text = path.read_text()
for old in (
    "runner.PILOT_VERSION = 'arch-aware-v1.26-adversarial'",
    "runner.PILOT_VERSION = 'arch-aware-v1.29-hidden-dramatic-adversarial'",
):
    text = text.replace(old, "runner.PILOT_VERSION = 'arch-aware-v1.30-cabbage-highfae-adversarial'")
if "arch-aware-v1.30-cabbage-highfae-adversarial" not in text:
    raise SystemExit('v1.30 pilot version replacement failed')
path.write_text(text)
print('applied arch-aware-v1.30-cabbage-highfae-adversarial identity')
