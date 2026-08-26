#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'
OUT = DECKS / 'Kinnan_ARCH_F10_HIDDEN_DRAMATIC_PACKAGE.dck'
CUTS = ['Misdirection', 'Energy Refractor']
ADDS = ['Hidden Strings', 'Dramatic Reversal']

lines = BASE.read_text().splitlines()
start = lines.index('[Main]') + 1
header = lines[:start]
cards = [line.split(' ', 1)[1].strip() for line in lines[start:] if line.strip()]
for card in CUTS:
    if card not in cards:
        raise SystemExit(f'missing cut: {card}')
    cards.remove(card)
for card in ADDS:
    if card in cards:
        raise SystemExit(f'duplicate add: {card}')
    cards.append(card)
if len(cards) != 99 or len(set(cards)) != 99:
    raise SystemExit(f'invalid deck: {len(cards)} cards, {len(set(cards))} unique')
header[1] = 'Name=Kinnan ARCH F10 Hidden Strings Dramatic Reversal Package'
OUT.write_text('\n'.join(header + [f'1 {c}' for c in cards]) + '\n')
print('F10_HIDDEN_DRAMATIC_PACKAGE cuts=', CUTS, 'adds=', ADDS)
