#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'
KEY = 'F10_SHANG_SPELLSKITE_PACKAGE'
CUTS = ['Misdirection', 'Energy Refractor']
ADDS = ['Shang-Chi, Master of Kung Fu', 'Spellskite']

lines = BASE.read_text().splitlines()
start = lines.index('[Main]') + 1
head = lines[:start]
cards = [line.split(' ', 1)[1] for line in lines[start:] if line.strip()]
assert len(cards) == 99 and len(set(cards)) == 99
for c in CUTS:
    assert c in cards, c
    cards.remove(c)
for c in ADDS:
    assert c not in cards, c
    cards.append(c)
assert len(cards) == 99 and len(set(cards)) == 99
if len(head) > 1 and head[1].startswith('Name='):
    head[1] = f'Name=Kinnan ARCH {KEY}'
out = DECKS / f'Kinnan_ARCH_{KEY}.dck'
out.write_text('\n'.join(head + [f'1 {c}' for c in cards]) + '\n')
print(KEY, 'cuts=', CUTS, 'adds=', ADDS)
