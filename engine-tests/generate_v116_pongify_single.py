#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
SRC = DECKS / 'Kinnan_ARCH_F10.dck'
DST = DECKS / 'Kinnan_ARCH_F10_PONGIFY_SINGLE.dck'

lines = SRC.read_text().splitlines()
start = lines.index('[Main]') + 1
header = lines[:start]
cards = [x.split(' ', 1)[1] for x in lines[start:] if x.strip()]
assert len(cards) == 99 and len(set(cards)) == 99
assert 'Energy Refractor' in cards
assert 'Pongify' not in cards
cards.remove('Energy Refractor')
cards.append('Pongify')
assert len(cards) == 99 and len(set(cards)) == 99
header[1] = 'Name=Kinnan ARCH F10 Pongify Single'
DST.write_text('\n'.join(header + [f'1 {c}' for c in cards]) + '\n')
print('F10_PONGIFY_SINGLE CHANGES 1 CUT Energy Refractor ADD Pongify')
