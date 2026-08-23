#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'
LABEL = 'F10_SNAPBACK_SINGLE'
CUT = 'Dispel'
ADD = 'Snapback'


def parse(path: Path):
    lines = path.read_text().splitlines()
    start = lines.index('[Main]') + 1
    header = lines[:start]
    cards = []
    for line in lines[start:]:
        if not line.strip():
            continue
        qty, name = line.split(' ', 1)
        cards.extend([name] * int(qty))
    return header, cards


def main():
    header, cards = parse(BASE)
    assert len(cards) == 99 and len(set(cards)) == 99
    if CUT not in cards: raise SystemExit(f'missing cut {CUT}')
    if ADD in cards: raise SystemExit(f'duplicate add {ADD}')
    cards.remove(CUT); cards.append(ADD)
    assert len(cards) == 99 and len(set(cards)) == 99
    h = list(header); h[1] = f'Name=Kinnan v1.15 Protection {LABEL}'
    out = DECKS / f'Kinnan_ARCH_{LABEL}.dck'
    out.write_text('\n'.join(h + [f'1 {card}' for card in cards]) + '\n')
    print(LABEL, 'CUT', CUT, 'ADD', ADD)


if __name__ == '__main__':
    main()
