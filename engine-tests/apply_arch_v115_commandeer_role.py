#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parent / 'manabrew_pilot.py'
s = p.read_text()
needle = "    'Mental Misstep','Mindbreak Trap','Daze','Pyroblast','Red Elemental Blast','Deflecting Swat','Deadly Rollick',\n"
replacement = "    'Mental Misstep','Mindbreak Trap','Daze','Commandeer','Pyroblast','Red Elemental Blast','Deflecting Swat','Deadly Rollick',\n"
if 'Commandeer' not in s:
    if needle not in s:
        raise SystemExit('interaction insertion point not found')
    s = s.replace(needle, replacement, 1)
p.write_text(s)
print('registered Commandeer as interaction')
