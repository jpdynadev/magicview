#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DECKS=ROOT/'decks'
BASE=DECKS/'Kinnan_TestB.dck'

# Incremental tutor packages. Keep the highest-value M25 protection intact.
# T2/T4/T6 are deliberately nested so we measure tutor density rather than unrelated card identity churn.
ORDERED_ADDS=['Reshape','Trinket Mage',"Green Sun's Zenith",'Eldritch Evolution','Spellseeker','Mystical Tutor']
# Cut slower/grindier or lower-connectivity cards first; do not cut the compact protection suite.
ORDERED_CUTS=['Faerie Mastermind','Prophet of Distortion','Seedborn Muse','Hullbreaker Horror','Hydroelectric Specimen','Mockingbird']
LEVELS={'T2':2,'T4':4,'T6':6}

def parse(text):
    lines=text.splitlines(); start=lines.index('[Main]')+1
    cards=[]
    for line in lines[start:]:
        line=line.strip()
        if not line: continue
        qty,name=line.split(' ',1); cards.extend([name]*int(qty))
    return lines[:start],cards

def main():
    header,base=parse(BASE.read_text())
    for key,n in LEVELS.items():
        cards=list(base)
        for c in ORDERED_CUTS[:n]:
            if c not in cards: raise SystemExit(f'{key}: missing cut {c}')
            cards.remove(c)
        for c in ORDERED_ADDS[:n]:
            if c in cards: raise SystemExit(f'{key}: duplicate add {c}')
            cards.append(c)
        if len(cards)!=99 or len(set(cards))!=99: raise SystemExit(f'{key}: invalid deck')
        h=list(header); h[1]=f'Name=Kinnan Tutor Sweep {key}'
        (DECKS/f'Kinnan_TUTOR_{key}.dck').write_text('\n'.join(h+[f'1 {c}' for c in cards])+'\n')
        print(key,'cuts',ORDERED_CUTS[:n],'adds',ORDERED_ADDS[:n])
if __name__=='__main__': main()
