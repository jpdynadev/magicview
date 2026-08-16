#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DECKS=ROOT/'decks'
BASE=DECKS/'Kinnan_TestB.dck'

# Reconstruct current champion F10_BLUE from M25/B0.
F10_CUT=['Faerie Mastermind','Prophet of Distortion','Seedborn Muse','Hullbreaker Horror']
F10_ADD=['Reshape','Trinket Mage','Spellseeker','Mystical Tutor']

# Precision mutations. Keep prior experiments for reproducibility and add
# tournament-derived candidates as small, interpretable tests.
SPECS={
 'P00_F10': ([],[]),
 'P01_MISCAST': (['Dispel'],['Miscast']),
 'P02_GSZ': (['Mystical Tutor'],["Green Sun's Zenith"]),
 'P03_ELDRITCH': (['Mystical Tutor'],['Eldritch Evolution']),
 'P04_TRIBUTE': (['Mystical Tutor'],['Tribute Mage']),
 'P05_SEEDBORN': (["Nature's Rhythm"],['Seedborn Muse']),
 'P06_HULLBREAKER': (['Mockingbird'],['Hullbreaker Horror']),
 'P07_M30_MICRO': (['Dispel','Mockingbird'],['Miscast','Consecrated Sphinx']),
 'P08_COPY_MOCK': (['Mockingbird'],['Copy Enchantment']),
 'P09_COPY_NATURE': (["Nature's Rhythm"],['Copy Enchantment']),
 'P10_RITE_NATURE': (["Nature's Rhythm"],['Cryptolith Rite']),
 'P11_WAN_NATURE': (["Nature's Rhythm"],['Wan Shi Tong, Librarian']),
 'P12_HIGHFAE_BORNE': (['Borne Upon a Wind'],['High Fae Trickster']),
 'P13_UNAGI_NATURE': (["Nature's Rhythm"],['The Unagi of Kyoshi Island']),
 'P14_COMMANDEER_MISD': (['Misdirection'],['Commandeer']),
 # Crossover suggested by repeated 2026 tournament co-adoption. Test whether
 # High Fae's permanent flash plus Wan's tutor-punish/value engine is synergistic
 # even though High Fae alone tied F10 in the latest ~800-game confirmation.
 'P15_HIGHFAE_WAN': (['Borne Upon a Wind',"Nature's Rhythm"],['High Fae Trickster','Wan Shi Tong, Librarian']),
 # Gene Pollinator is a tournament-supported Kinnan-specific mana converter.
 # Compare it directly to Springleaf Drum to keep the role/CMC nearly constant.
 'P16_GENE_DRUM': (['Springleaf Drum'],['Gene Pollinator']),
 # P14 showed that replacing Misdirection with Commandeer was a bad trade.
 # Successful current Kinnan shells frequently keep Misdirection and Commandeer
 # together, so isolate the question of whether a second free blue permission
 # spell is better than the narrower one-mana Dispel slot.
 'P17_COMMANDEER_DISPEL': (['Dispel'],['Commandeer']),
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
