#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'
OUT = DECKS / 'Kinnan_ARCH_F10_DRUID_EFFIGY_HYBRID.dck'

CUTS = ['Valley Floodcaller', "Nature's Rhythm"]
ADDS = ['Devoted Druid', "Machine God's Effigy"]

lines = BASE.read_text().splitlines()
start = lines.index('[Main]') + 1
header = lines[:start]
cards = [x.split(' ',1)[1] for x in lines[start:] if x.strip()]
for card in CUTS:
    if card not in cards:
        raise SystemExit(f'missing cut {card}')
    cards.remove(card)
for card in ADDS:
    if card in cards:
        raise SystemExit(f'duplicate add {card}')
    cards.append(card)
if len(cards) != 99 or len(set(cards)) != 99:
    raise SystemExit((len(cards), len(set(cards))))
header[1] = 'Name=Kinnan ARCH F10 Druid Effigy Hybrid'
OUT.write_text('\n'.join(header + [f'1 {c}' for c in cards]) + '\n')
print('F10_DRUID_EFFIGY_HYBRID CUT', CUTS, 'ADD', ADDS)
