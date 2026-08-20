#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_TestB.dck'

# Rebuild the validated F10_BLUE baseline first, then make larger architecture-
# level mutations. This intentionally avoids trying to infer singleton value
# from tiny samples.
F10_CUTS = ['Faerie Mastermind', 'Prophet of Distortion', 'Seedborn Muse', 'Hullbreaker Horror']
F10_ADDS = ['Reshape', 'Trinket Mage', 'Spellseeker', 'Mystical Tutor']

SPECS = {
    'F10': ([], []),
    'COPY_CORE': (
        ["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum'],
        ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Mirage Mirror'],
    ),
    'COPY_CREATURE': (
        ["Nature's Rhythm", 'Energy Refractor', 'Dispel'],
        ['Flesh Duplicate', 'Clever Impersonator', 'Gene Pollinator'],
    ),
    'DRUID_EFFIGY': (
        ["Nature's Rhythm", 'Energy Refractor', 'Dispel'],
        ['Devoted Druid', "Machine God's Effigy", 'Gene Pollinator'],
    ),
    'COPY_DRUID': (
        ["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection'],
        ['Devoted Druid', "Machine God's Effigy", 'Flesh Duplicate', 'Copy Enchantment', 'Gene Pollinator'],
    ),
    'COPY_HEAVY': (
        ["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection', 'Hydroelectric Specimen'],
        ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Mirage Mirror', 'Clever Impersonator', 'Gene Pollinator'],
    ),
    'COPY_ARTIFACT': (
        ["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Hydroelectric Specimen'],
        ['Copy Artifact', 'Mirage Mirror', 'Phyrexian Metamorph', 'Flesh Duplicate'],
    ),
    'COPY_PROTECTED': (
        ["Nature's Rhythm", 'Energy Refractor', 'Springleaf Drum', 'Hydroelectric Specimen'],
        ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Gene Pollinator'],
    ),
    'DRUID_TUTOR': (
        ['Energy Refractor', 'Dispel', 'Springleaf Drum', 'Hydroelectric Specimen'],
        ['Devoted Druid', "Machine God's Effigy", "Green Sun's Zenith", 'Eldritch Evolution'],
    ),
    'TUTOR_DENSE': (
        ['Energy Refractor', 'Dispel', 'Springleaf Drum', 'Hydroelectric Specimen'],
        ["Green Sun's Zenith", 'Eldritch Evolution', 'Tribute Mage', 'Devoted Druid'],
    ),
    'NODE_DENSE': (
        ["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection', 'Hydroelectric Specimen'],
        ['Devoted Druid', "Machine God's Effigy", 'Copy Artifact', 'Flesh Duplicate', "Green Sun's Zenith", 'Eldritch Evolution'],
    ),
    'COPY_VALUE': (
        ["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Hydroelectric Specimen'],
        ['Copy Enchantment', 'Flesh Duplicate', 'Clever Impersonator', 'Gene Pollinator'],
    ),
    # New F10-derived packages: unlike the older copy architectures these keep
    # Nature's Rhythm / Chord / Transmute Artifact, which are already in F10.
    # They target the empirically weaker F10 exposure slots instead of cutting
    # tutor-quality cards merely to raise clone density.
    'F10_COPY_COMPACT': (
        ['Reshape', 'Spellseeker', 'Energy Refractor'],
        ['Clever Impersonator', 'Flesh Duplicate', 'Copy Enchantment'],
    ),
    'F10_DRUID_COMPACT': (
        ['Reshape', 'Spellseeker', 'Energy Refractor', 'Hydroelectric Specimen'],
        ['Devoted Druid', "Machine God's Effigy", "Green Sun's Zenith", 'Eldritch Evolution'],
    ),
    'F10_COPY_TUTOR': (
        ['Reshape', 'Spellseeker', 'Energy Refractor', 'Hydroelectric Specimen'],
        ['Clever Impersonator', 'Flesh Duplicate', "Green Sun's Zenith", 'Eldritch Evolution'],
    ),
}

# Every experimentally added card must have an explicit semantic role in the
# architecture-aware pilot. Unknown cards are a hard error rather than a silent
# hand-score fallback.
REGISTERED_ADDS = {
    'Reshape', 'Trinket Mage', 'Spellseeker', 'Mystical Tutor', "Green Sun's Zenith",
    'Eldritch Evolution', 'Tribute Mage', 'Copy Enchantment', 'Copy Artifact',
    'Flesh Duplicate', 'Mirage Mirror', 'Clever Impersonator', 'Gene Pollinator',
    'Phyrexian Metamorph', 'Devoted Druid', "Machine God's Effigy",
}


def parse(text: str):
    lines = text.splitlines()
    start = lines.index('[Main]') + 1
    cards = []
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        qty, name = line.split(' ', 1)
        cards.extend([name] * int(qty))
    return lines[:start], cards


def mutate(cards, cuts, adds, label):
    out = list(cards)
    for card in cuts:
        if card not in out:
            raise SystemExit(f'{label}: missing cut {card}')
        out.remove(card)
    for card in adds:
        if card not in REGISTERED_ADDS:
            raise SystemExit(f'{label}: unregistered experimental card {card}')
        if card in out:
            raise SystemExit(f'{label}: duplicate add {card}')
        out.append(card)
    if len(out) != 99 or len(set(out)) != 99:
        raise SystemExit(f'{label}: invalid deck count={len(out)} unique={len(set(out))}')
    return out


def main():
    header, base_cards = parse(BASE.read_text())
    f10 = mutate(base_cards, F10_CUTS, F10_ADDS, 'F10_BASE')
    for key, (cuts, adds) in SPECS.items():
        cards = mutate(f10, cuts, adds, key)
        h = list(header)
        h[1] = f'Name=Kinnan Expanded Architecture {key}'
        path = DECKS / f'Kinnan_ARCH_{key}.dck'
        path.write_text('\n'.join(h + [f'1 {card}' for card in cards]) + '\n')
        print(key, 'CHANGES', len(cuts), 'CUT', cuts, 'ADD', adds)


if __name__ == '__main__':
    main()
