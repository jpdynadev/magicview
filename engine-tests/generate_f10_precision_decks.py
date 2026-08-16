#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DECKS=ROOT/'decks'
BASE=DECKS/'Kinnan_TestB.dck'

# Reconstruct current champion F10_BLUE from M25/B0.
F10_CUT=['Faerie Mastermind','Prophet of Distortion','Seedborn Muse','Hullbreaker Horror']
F10_ADD=['Reshape','Trinket Mage','Spellseeker','Mystical Tutor']

# Precision mutations: mostly one-card deltas from F10, deliberately chosen to
# isolate interaction quality, tutor identity, and whether restoring a premium
# Kinnan/value hit improves real conversion without undoing the tutor package.
SPECS={
 'P00_F10': ([],[]),
 # One-card interaction substitution; Miscast was part of the strong M2K0030/F14 signal.
 'P01_MISCAST': (['Dispel'],['Miscast']),
 # One-card tutor identity substitutions around the four-tutor sweet spot.
 'P02_GSZ': (['Mystical Tutor'],["Green Sun's Zenith"]),
 'P03_ELDRITCH': (['Mystical Tutor'],['Eldritch Evolution']),
 'P04_TRIBUTE': (['Mystical Tutor'],['Tribute Mage']),
 # Restore value/engine cards F10 cut, using lower-connectivity flex slots.
 'P05_SEEDBORN': (["Nature's Rhythm"],['Seedborn Muse']),
 'P06_HULLBREAKER': (['Mockingbird'],['Hullbreaker Horror']),
 # Best-looking two-card crossover from the M2K0030/F14 direction.
 'P07_M30_MICRO': (['Dispel','Mockingbird'],['Miscast','Consecrated Sphinx']),
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
    # The external-comparison workflow writes tiny wrapper scripts into /tmp.
    # Python resolves imports relative to that wrapper location, so expose the
    # engine-test modules there on this isolated comparison branch.
    tmp=Path('/tmp')
    for module in ROOT.glob('*.py'):
        target=tmp/module.name
        if not target.exists():
            target.symlink_to(module)

    header,base=parse(BASE.read_text())
    f10=apply(base,F10_CUT,F10_ADD,'F10')
    for key,(cuts,adds) in SPECS.items():
        cards=apply(f10,cuts,adds,key)
        h=list(header); h[1]=f'Name=Kinnan F10 Precision {key}'
        out=DECKS/f'Kinnan_PREC_{key}.dck'
        out.write_text('\n'.join(h+[f'1 {c}' for c in cards])+'\n')
        print(key,'CUT_FROM_F10',cuts,'ADD_TO_F10',adds)

if __name__=='__main__': main()
