from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
SRC = DECKS / 'Kinnan_ARCH_F10.dck'
DST = DECKS / 'Kinnan_ARCH_F10_CLEVER_CYCLONIC_PACKAGE.dck'

CUTS = ['Energy Refractor', "Nature's Rhythm"]
ADDS = ['Clever Impersonator', 'Cyclonic Rift']

lines = SRC.read_text().splitlines()
start = lines.index('[Main]') + 1
head = lines[:start]
cards = [x.split(' ', 1)[1] for x in lines[start:] if x.strip()]
for c in CUTS:
    if c not in cards:
        raise SystemExit(f'missing cut: {c}')
    cards.remove(c)
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
