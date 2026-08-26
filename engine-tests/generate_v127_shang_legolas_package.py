#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DECKS=ROOT/'decks'; BASE=DECKS/'Kinnan_ARCH_F10.dck'
KEY='F10_SHANG_LEGOLAS_PACKAGE'
CUTS=["Nature's Rhythm",'Endurance']
ADDS=['Shang-Chi, Master of Kung Fu',"Legolas's Quick Reflexes"]
lines=BASE.read_text().splitlines(); start=lines.index('[Main]')+1; header=lines[:start]
cards=[x.split(' ',1)[1] for x in lines[start:] if x.strip()]
for cut in CUTS:
    if cut not in cards: raise SystemExit(f'{KEY}: missing cut {cut}')
    cards.remove(cut)
for add in ADDS:
    if add in cards: raise SystemExit(f'{KEY}: duplicate add {add}')
    cards.append(add)
if len(cards)!=99 or len(set(cards))!=99: raise SystemExit(f'{KEY}: invalid 99 {len(cards)} {len(set(cards))}')
h=list(header); h[1]=f'Name=Kinnan {KEY}'
out=DECKS/f'Kinnan_ARCH_{KEY}.dck'; out.write_text('\n'.join(h+[f'1 {c}' for c in cards])+'\n')
print(KEY,'cuts=',CUTS,'adds=',ADDS)
