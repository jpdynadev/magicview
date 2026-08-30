#!/usr/bin/env python3
from pathlib import Path
ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'
OUT = DECKS / 'Kinnan_ARCH_F10_RING_SINGLE.dck'
CUTS = ['Endurance']
ADDS = ['The One Ring']
lines = BASE.read_text().splitlines(); start = lines.index('[Main]') + 1
header = lines[:start]
cards = [line.split(' ',1)[1] for line in lines[start:] if line.strip()]
for card in CUTS:
    if card not in cards: raise SystemExit(f'missing cut: {card}')
    cards.remove(card)
for card in ADDS:
    if card in cards: raise SystemExit(f'duplicate add: {card}')
    cards.append(card)
if len(cards) != 99 or len(set(cards)) != 99:
    raise SystemExit(f'invalid 99: {len(cards)} cards, {len(set(cards))} unique')
header[1] = 'Name=Kinnan F10 Ring Single'
OUT.write_text('\n'.join(header + [f'1 {c}' for c in cards]) + '\n')
print('wrote', OUT, 'cuts=', CUTS, 'adds=', ADDS)
