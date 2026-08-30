#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'
OUT = DECKS / 'Kinnan_ARCH_F10_CABBAGE_HIGHFAE_PACKAGE.dck'
CUTS = ['Misdirection', 'Energy Refractor']
ADDS = ['The Cabbage Merchant', 'High Fae Trickster']

lines = BASE.read_text().splitlines()
start = lines.index('[Main]') + 1
header = lines[:start]
cards = [x.split(' ', 1)[1] for x in lines[start:] if x.strip()]
for card in CUTS:
    if card not in cards:
        raise SystemExit(f'missing cut {card}')
    cards.remove(card)
for card in ADDS:
    if card in cards:
        raise SystemExit(f'duplicate add {card}')
    cards.append(card)
assert len(cards) == 99 and len(set(cards)) == 99, (len(cards), len(set(cards)))
header[1] = 'Name=Kinnan ARCH F10 Cabbage High Fae Package'
OUT.write_text('\n'.join(header + [f'1 {c}' for c in cards]) + '\n')
print('wrote', OUT, 'cuts=', CUTS, 'adds=', ADDS)
