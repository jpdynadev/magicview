#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'

VARIANTS = {
    'F10_SHOAL_SINGLE': ('Dispel', 'Disrupting Shoal'),
}


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
    header, base = parse(BASE)
    assert len(base) == 99 and len(set(base)) == 99
    for label, (cut, add) in VARIANTS.items():
        cards = list(base)
        if cut not in cards:
            raise SystemExit(f'{label}: missing cut {cut}')
        if add in cards:
            raise SystemExit(f'{label}: duplicate add {add}')
        cards.remove(cut)
        cards.append(add)
        assert len(cards) == 99 and len(set(cards)) == 99
        h = list(header)
        h[1] = f'Name=Kinnan v1.15 Protection {label}'
        out = DECKS / f'Kinnan_ARCH_{label}.dck'
        out.write_text('\n'.join(h + [f'1 {card}' for card in cards]) + '\n')
        print(label, 'CUT', cut, 'ADD', add)


if __name__ == '__main__':
    main()
