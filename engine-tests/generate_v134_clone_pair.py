#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'
OUT = DECKS / 'Kinnan_ARCH_F10_CLONE_PAIR.dck'
CUTS = ['Misdirection', "Nature's Rhythm"]
ADDS = ['Flesh Duplicate', 'Clever Impersonator']


def main():
    lines = BASE.read_text().splitlines()
    start = lines.index('[Main]') + 1
    header = lines[:start]
    cards = [line.split(' ', 1)[1] for line in lines[start:] if line.strip()]
    assert len(cards) == 99 and len(set(cards)) == 99, (len(cards), len(set(cards)))
    for card in CUTS:
        assert card in cards, f'missing cut {card}'
        cards.remove(card)
    for card in ADDS:
        assert card not in cards, f'duplicate add {card}'
        cards.append(card)
    assert len(cards) == 99 and len(set(cards)) == 99, (len(cards), len(set(cards)))
    header = list(header)
    header[1] = 'Name=Kinnan F10 Flexible Clone Pair'
    OUT.write_text('\n'.join(header + [f'1 {card}' for card in cards]) + '\n')
    print('F10_CLONE_PAIR', 'CUT', CUTS, 'ADD', ADDS)


if __name__ == '__main__':
    main()
