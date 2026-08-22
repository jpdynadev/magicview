#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DECKS=ROOT/'decks'
BASE=DECKS/'Kinnan_TestB.dck'

# Focused local search around the two strongest empirical signals:
# (1) +4 tutors outperformed +0/+2/+6 in the paired tutor sweep.
# (2) M2K0030 was the strongest adversarial challenger.
# We vary tutor identity, cut identity, and whether the M2K0030 package stacks with tutors.

T4=['Reshape','Trinket Mage',"Green Sun's Zenith",'Eldritch Evolution']
ALT_SPELL=['Reshape','Trinket Mage',"Green Sun's Zenith",'Spellseeker']
ALT_MYST=['Reshape','Trinket Mage',"Green Sun's Zenith",'Mystical Tutor']
ALT_CREATURE=['Reshape',"Green Sun's Zenith",'Eldritch Evolution','Spellseeker']
ALT_ARTIFACT=['Reshape','Trinket Mage','Tribute Mage',"Green Sun's Zenith"]
ALT_BLUE=['Reshape','Trinket Mage','Spellseeker','Mystical Tutor']

CUT_EXACT=['Faerie Mastermind','Prophet of Distortion','Seedborn Muse','Hullbreaker Horror']
CUT_LIGHT=['Faerie Mastermind','Prophet of Distortion','Hydroelectric Specimen','Mockingbird']
CUT_MIX=['Faerie Mastermind','Seedborn Muse','Hydroelectric Specimen','Mockingbird']
CUT_ENGINE=['Prophet of Distortion','Seedborn Muse','Hydroelectric Specimen','Mockingbird']
CUT_UTILITY=['Faerie Mastermind','Prophet of Distortion','Defense Grid','Energy Refractor']

SPECS={
 'F01_T4_EXACT': (CUT_EXACT,T4),
 'F02_T4_LIGHT': (CUT_LIGHT,T4),
 'F03_T4_MIX': (CUT_MIX,T4),
 'F04_T4_ENGINE': (CUT_ENGINE,T4),
 'F05_T4_UTILITY': (CUT_UTILITY,T4),
 'F06_SPELL': (CUT_EXACT,ALT_SPELL),
 'F07_MYST': (CUT_EXACT,ALT_MYST),
 'F08_CREATURE': (CUT_EXACT,ALT_CREATURE),
 'F09_ARTIFACT': (CUT_EXACT,ALT_ARTIFACT),
 'F10_BLUE': (CUT_EXACT,ALT_BLUE),
 # M2K0030 reconstruction from the screened mutation: Chain of Vapor + Goblin Cannon
 # -> Consecrated Sphinx + Miscast.
 'F11_M30': (['Chain of Vapor','Goblin Cannon'],['Consecrated Sphinx','Miscast']),
 'F12_M30_T4': (['Chain of Vapor','Goblin Cannon']+CUT_EXACT,['Consecrated Sphinx','Miscast']+T4),
 'F13_M30_LIGHT': (['Chain of Vapor','Goblin Cannon']+CUT_LIGHT,['Consecrated Sphinx','Miscast']+T4),
 'F14_M30_SPELL': (['Chain of Vapor','Goblin Cannon']+CUT_EXACT,['Consecrated Sphinx','Miscast']+ALT_SPELL),
 'F15_M30_ART': (['Chain of Vapor','Goblin Cannon']+CUT_EXACT,['Consecrated Sphinx','Miscast']+ALT_ARTIFACT),
}

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
    for key,(cuts,adds) in SPECS.items():
        cards=list(base)
        for c in cuts:
            if c not in cards: raise SystemExit(f'{key}: missing cut {c}')
            cards.remove(c)
        for c in adds:
            if c in cards: raise SystemExit(f'{key}: duplicate add {c}')
            cards.append(c)
        if len(cards)!=99 or len(set(cards))!=99:
            raise SystemExit(f'{key}: invalid deck count={len(cards)} unique={len(set(cards))}')
        h=list(header); h[1]=f'Name=Kinnan Focused99 {key}'
        out=DECKS/f'Kinnan_F99_{key}.dck'
        out.write_text('\n'.join(h+[f'1 {c}' for c in cards])+'\n')
        print(key,'CUT',cuts,'ADD',adds)

if __name__=='__main__': main()
