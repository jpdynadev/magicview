from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
SRC = DECKS / 'Kinnan_ARCH_F10.dck'
DST = DECKS / 'Kinnan_ARCH_F10_CREATURE_COPY_ARCH.dck'

CUTS = [
    'Fabricate',
    'Reshape',
    'Transmute Artifact',
    'Energy Refractor',
    "Nature's Rhythm",
    'Misdirection',
]
ADDS = [
    'Seedborn Muse',
    'Glen Elendra Archmage',
    'Sylvan Safekeeper',
    'Spellskite',
    'Flesh Duplicate',
    'Clever Impersonator',
]

lines = SRC.read_text().splitlines()
start = lines.index('[Main]') + 1
head = lines[:start]
main = [x for x in lines[start:] if x.strip()]

def card_name(line):
    return line.split(' ', 1)[1]

cards = [card_name(x) for x in main]
for c in CUTS:
    if c not in cards:
        raise SystemExit(f'missing cut: {c}')
    i = cards.index(c)
    cards.pop(i)
for c in ADDS:
    if c in cards:
        raise SystemExit(f'duplicate add: {c}')
    cards.append(c)

if len(cards) != 99 or len(set(cards)) != 99:
    raise SystemExit(f'bad singleton deck: {len(cards)} cards / {len(set(cards))} unique')

DST.write_text('\n'.join(head + [f'1 {c}' for c in cards]) + '\n')
print('wrote', DST)
print('cuts:', ', '.join(CUTS))
print('adds:', ', '.join(ADDS))
