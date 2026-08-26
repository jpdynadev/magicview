#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DECKS=ROOT/'decks'; BASE=DECKS/'Kinnan_ARCH_F10.dck'
VARIANTS={
 'F10_RING_OVER_RHYTHM':("Nature's Rhythm",'The One Ring'),
 'F10_RING_OVER_ENDURANCE':('Endurance','The One Ring'),
}
lines=BASE.read_text().splitlines(); start=lines.index('[Main]')+1; header=lines[:start]
base=[x.split(' ',1)[1] for x in lines[start:] if x.strip()]
for key,(cut,add) in VARIANTS.items():
 cards=list(base)
 if cut not in cards: raise SystemExit(f'{key}: missing cut {cut}')
 if add in cards: raise SystemExit(f'{key}: duplicate add {add}')
 cards.remove(cut); cards.append(add)
 if len(cards)!=99 or len(set(cards))!=99: raise SystemExit(f'{key}: invalid 99')
 h=list(header); h[1]=f'Name=Kinnan {key}'
 out=DECKS/f'Kinnan_ARCH_{key}.dck'; out.write_text('\n'.join(h+[f'1 {c}' for c in cards])+'\n')
 print(key,'cut=',cut,'add=',add)
