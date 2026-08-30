#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_TestB.dck'

EXPERIMENTS = {
    'DORKMAX': {
        'cuts': ['Faerie Mastermind','Prophet of Distortion','Seedborn Muse','Hullbreaker Horror','Hydroelectric Specimen','Mockingbird','Defense Grid','Sylvan Library',"Nature's Rhythm",'Tezzeret the Seeker'],
        'adds': ['Arbor Elf','Boreal Druid','Paradise Druid','Incubation Druid','Priest of Titania',"Kiora's Follower",'Devoted Druid','Wall of Roots','Elvish Archdruid','Gyre Engineer'],
    },
    'TUTORMAX': {
        'cuts': ['Faerie Mastermind','Prophet of Distortion','Seedborn Muse','Hullbreaker Horror','Hydroelectric Specimen','Mockingbird','Defense Grid','Energy Refractor','Sylvan Library','Borne Upon a Wind'],
        'adds': ['Reshape','Trinket Mage','Tribute Mage',"Green Sun's Zenith",'Eldritch Evolution','Spellseeker','Mystical Tutor','Merchant Scroll','Personal Tutor','Solve the Equation'],
    },
    'MESHMAX': {
        'cuts': ['Faerie Mastermind','Prophet of Distortion','Seedborn Muse','Hydroelectric Specimen','Mockingbird','Defense Grid','Energy Refractor','Sylvan Library',"Nature's Rhythm",'Misdirection'],
        'adds': ['Rings of Brighthearth','Freed from the Real',"Pemmin's Aura",'Nyxbloom Ancient',"Blue Sun's Zenith",'Reshape','Trinket Mage','Tribute Mage','Training Grounds',"Biomancer's Familiar"],
    },
}

def parse_cards(text):
    lines = text.splitlines()
    start = lines.index('[Main]') + 1
    cards = []
    for line in lines[start:]:
        line=line.strip()
        if not line: continue
        qty, name = line.split(' ',1)
        cards.extend([name]*int(qty))
    return lines[:start], cards

def write_variant(key, spec):
    header, cards = parse_cards(BASE.read_text())
    for cut in spec['cuts']:
        if cut not in cards:
            raise SystemExit(f'{key}: missing cut {cut}')
        cards.remove(cut)
    for add in spec['adds']:
        if add in cards:
            raise SystemExit(f'{key}: duplicate add {add}')
        cards.append(add)
    if len(cards) != 99 or len(set(cards)) != 99:
        raise SystemExit(f'{key}: invalid main count {len(cards)} unique {len(set(cards))}')
    header[1] = f'Name=Kinnan Lever {key}'
    out = DECKS / f'Kinnan_LEVER_{key}.dck'
    out.write_text('\n'.join(header + [f'1 {c}' for c in cards]) + '\n')
    print(key, 'cuts=', spec['cuts'], 'adds=', spec['adds'])

if __name__ == '__main__':
    for key,spec in EXPERIMENTS.items(): write_variant(key,spec)
