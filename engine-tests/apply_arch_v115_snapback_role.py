#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parent / 'manabrew_pilot.py'
s = p.read_text()
needle = "    'Chain of Vapor','Into the Flood Maw','Snap','Veil of Summer','Borne Upon a Wind'\n"
replacement = "    'Chain of Vapor','Into the Flood Maw','Snap','Snapback','Veil of Summer','Borne Upon a Wind'\n"
if 'Snapback' not in s:
    if needle not in s:
        raise SystemExit('interaction insertion point not found')
    s = s.replace(needle, replacement, 1)
p.write_text(s)
print('registered Snapback as interaction')
