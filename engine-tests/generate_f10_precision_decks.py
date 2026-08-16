#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DECKS=ROOT/'decks'
BASE=DECKS/'Kinnan_TestB.dck'

# Reconstruct current champion F10_BLUE from M25/B0.
F10_CUT=['Faerie Mastermind','Prophet of Distortion','Seedborn Muse','Hullbreaker Horror']
F10_ADD=['Reshape','Trinket Mage','Spellseeker','Mystical Tutor']

# Precision mutations. Keep prior experiments for reproducibility and add
# tournament-derived candidates as isolated one-card tests.
SPECS={
 'P00_F10': ([],[]),
 'P01_MISCAST': (['Dispel'],['Miscast']),
 'P02_GSZ': (['Mystical Tutor'],["Green Sun's Zenith"]),
 'P03_ELDRITCH': (['Mystical Tutor'],['Eldritch Evolution']),
 'P04_TRIBUTE': (['Mystical Tutor'],['Tribute Mage']),
 'P05_SEEDBORN': (["Nature's Rhythm"],['Seedborn Muse']),
 'P06_HULLBREAKER': (['Mockingbird'],['Hullbreaker Horror']),
 'P07_M30_MICRO': (['Dispel','Mockingbird'],['Miscast','Consecrated Sphinx']),
 # 2026 tournament-derived Copy Enchantment slot tests.
 'P08_COPY_MOCK': (['Mockingbird'],['Copy Enchantment']),
 'P09_COPY_NATURE': (["Nature's Rhythm"],['Copy Enchantment']),
 # Cryptolith Rite appears in recent high-finishing Kinnan lists. Test the card
 # itself without importing the broader untapper package.
 'P10_RITE_NATURE': (["Nature's Rhythm"],['Cryptolith Rite']),
}

def parse(text):
    lines=text.splitlines(); start=lines.index('[Main]')+1
    cards=[]
    for line in lines[start:]:
        line=line.strip()
        if not line: continue
        qty,name=line.split(' ',1); cards.extend([name]*int(qty))
    return lines[:start],cards

def apply(cards,cuts,adds,label):
    cards=list(cards)
    for c in cuts:
        if c not in cards: raise SystemExit(f'{label}: missing cut {c}')
        cards.remove(c)
    for c in adds:
        if c in cards: raise SystemExit(f'{label}: duplicate add {c}')
        cards.append(c)
    if len(cards)!=99 or len(set(cards))!=99:
        raise SystemExit(f'{label}: invalid deck count={len(cards)} unique={len(set(cards))}')
    return cards

def main():
    header,base=parse(BASE.read_text())
    f10=apply(base,F10_CUT,F10_ADD,'F10')
    for key,(cuts,adds) in SPECS.items():
        cards=apply(f10,cuts,adds,key)
        h=list(header); h[1]=f'Name=Kinnan F10 Precision {key}'
        out=DECKS/f'Kinnan_PREC_{key}.dck'
        out.write_text('\n'.join(h+[f'1 {c}' for c in cards])+'\n')
        print(key,'CUT_FROM_F10',cuts,'ADD_TO_F10',adds)

if __name__=='__main__': main()
