#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_ARCH_F10.dck'

EXPERIMENTS = {
    'F10_SHANG_OVER_RHYTHM': {
        'cuts': ["Nature's Rhythm"],
        'adds': ['Shang-Chi, Master of Kung Fu'],
    },
    'F10_SHANG_OVER_ENDURANCE': {
        'cuts': ['Endurance'],
        'adds': ['Shang-Chi, Master of Kung Fu'],
    },
}

def parse(path: Path):
    lines = path.read_text().splitlines()
    start = lines.index('[Main]') + 1
    head = lines[:start]
    cards = [line.split(' ', 1)[1] for line in lines[start:] if line.strip()]
    return head, cards

def main():
    head, original = parse(BASE)
    assert len(original) == 99 and len(set(original)) == 99
    for key, spec in EXPERIMENTS.items():
        cards = list(original)
        for cut in spec['cuts']:
            assert cut in cards, (key, 'missing cut', cut)
            cards.remove(cut)
        for add in spec['adds']:
            assert add not in cards, (key, 'duplicate add', add)
            cards.append(add)
        assert len(cards) == 99 and len(set(cards)) == 99, (key, len(cards), len(set(cards)))
        out_head = list(head)
        if len(out_head) > 1 and out_head[1].startswith('Name='):
            out_head[1] = f'Name=Kinnan ARCH {key}'
        out = DECKS / f'Kinnan_ARCH_{key}.dck'
        out.write_text('\n'.join(out_head + [f'1 {c}' for c in cards]) + '\n')
        print(key, 'cuts=', spec['cuts'], 'adds=', spec['adds'])

if __name__ == '__main__':
    main()
