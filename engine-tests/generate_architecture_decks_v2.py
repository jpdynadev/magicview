#!/usr/bin/env python3
import os
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / 'decks'
BASE = DECKS / 'Kinnan_TestB.dck'

# Rebuild the validated F10_BLUE baseline first, then make larger architecture-
# level mutations. This intentionally avoids trying to infer singleton value
# from tiny samples.
F10_CUTS = ['Faerie Mastermind', 'Prophet of Distortion', 'Seedborn Muse', 'Hullbreaker Horror']
F10_ADDS = ['Reshape', 'Trinket Mage', 'Spellseeker', 'Mystical Tutor']

SPECS = {
    'F10': ([], []),
    'TURBO_F10': (
        ['Tezzeret the Seeker', 'Rhystic Study', 'Sylvan Library', 'Energy Refractor', 'Hydroelectric Specimen'],
        ["Green Sun's Zenith", 'Eldritch Evolution', 'Tribute Mage', 'Devoted Druid', 'Copy Artifact'],
    ),
    'COPY_CORE': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum'], ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Mirage Mirror']),
    'COPY_CREATURE': (["Nature's Rhythm", 'Energy Refractor', 'Dispel'], ['Flesh Duplicate', 'Clever Impersonator', 'Gene Pollinator']),
    'DRUID_EFFIGY': (["Nature's Rhythm", 'Energy Refractor', 'Dispel'], ['Devoted Druid', "Machine God's Effigy", 'Gene Pollinator']),
    'COPY_DRUID': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection'], ['Devoted Druid', "Machine God's Effigy", 'Flesh Duplicate', 'Copy Enchantment', 'Gene Pollinator']),
    'COPY_HEAVY': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection', 'Hydroelectric Specimen'], ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Mirage Mirror', 'Clever Impersonator', 'Gene Pollinator']),
    'COPY_ARTIFACT': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Hydroelectric Specimen'], ['Copy Artifact', 'Mirage Mirror', 'Phyrexian Metamorph', 'Flesh Duplicate']),
    'COPY_PROTECTED': (["Nature's Rhythm", 'Energy Refractor', 'Springleaf Drum', 'Hydroelectric Specimen'], ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Gene Pollinator']),
    'DRUID_TUTOR': (['Energy Refractor', 'Dispel', 'Springleaf Drum', 'Hydroelectric Specimen'], ['Devoted Druid', "Machine God's Effigy", "Green Sun's Zenith", 'Eldritch Evolution']),
    'TUTOR_DENSE': (['Energy Refractor', 'Dispel', 'Springleaf Drum', 'Hydroelectric Specimen'], ["Green Sun's Zenith", 'Eldritch Evolution', 'Tribute Mage', 'Devoted Druid']),
    'NODE_DENSE': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection', 'Hydroelectric Specimen'], ['Devoted Druid', "Machine God's Effigy", 'Copy Artifact', 'Flesh Duplicate', "Green Sun's Zenith", 'Eldritch Evolution']),
    'COPY_VALUE': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Hydroelectric Specimen'], ['Copy Enchantment', 'Flesh Duplicate', 'Clever Impersonator', 'Gene Pollinator']),
    'F10_COPY_COMPACT': (['Reshape', 'Spellseeker', 'Energy Refractor'], ['Clever Impersonator', 'Flesh Duplicate', 'Copy Enchantment']),
    'F10_DRUID_COMPACT': (['Reshape', 'Spellseeker', 'Energy Refractor', 'Hydroelectric Specimen'], ['Devoted Druid', "Machine God's Effigy", "Green Sun's Zenith", 'Eldritch Evolution']),
    'F10_COPY_TUTOR': (['Reshape', 'Spellseeker', 'Energy Refractor', 'Hydroelectric Specimen'], ['Clever Impersonator', 'Flesh Duplicate', "Green Sun's Zenith", 'Eldritch Evolution']),
    # Minimal F10-preserving tutor-quality test after broader Druid/clone packages
    # failed to improve protected T4 conversion at large sample sizes.
    'F10_TUTOR_PAIR': (
        ['Energy Refractor', 'Hydroelectric Specimen'],
        ["Green Sun's Zenith", 'Eldritch Evolution'],
    ),
    # Singleton isolation after the two-card Tutor Pair screen was flat/worse.
    # These identify whether one tutor is useful and the other is carrying the cost.
    'F10_GSZ_SINGLE': (
        ['Energy Refractor'],
        ["Green Sun's Zenith"],
    ),
    'F10_EVOLUTION_SINGLE': (
        ['Hydroelectric Specimen'],
        ['Eldritch Evolution'],
    ),
}

REGISTERED_ADDS = {
    'Reshape', 'Trinket Mage', 'Spellseeker', 'Mystical Tutor', "Green Sun's Zenith",
    'Eldritch Evolution', 'Tribute Mage', 'Copy Enchantment', 'Copy Artifact',
    'Flesh Duplicate', 'Mirage Mirror', 'Clever Impersonator', 'Gene Pollinator',
    'Phyrexian Metamorph', 'Devoted Druid', "Machine God's Effigy",
}


def parse(text: str):
    lines = text.splitlines()
    start = lines.index('[Main]') + 1
    cards = []
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        qty, name = line.split(' ', 1)
        cards.extend([name] * int(qty))
    return lines[:start], cards


def mutate(cards, cuts, adds, label):
    out = list(cards)
    for card in cuts:
        if card not in out:
            raise SystemExit(f'{label}: missing cut {card}')
        out.remove(card)
    for card in adds:
        if card not in REGISTERED_ADDS:
            raise SystemExit(f'{label}: unregistered experimental card {card}')
        if card in out:
            raise SystemExit(f'{label}: duplicate add {card}')
        out.append(card)
    if len(out) != 99 or len(set(out)) != 99:
        raise SystemExit(f'{label}: invalid deck count={len(out)} unique={len(set(out))}')
    return out


def prepare_profile_pilot():
    """Materialize runtime-only pilot patches required by profile-specific jobs.

    The v1.13 Evolution 2k workflow intentionally keeps v1.12/v1.13 changes as
    narrow patch scripts. Both build and confirm jobs invoke this generator, so
    applying them here for only that exact profile guarantees every fresh job
    uses the same validated pilot identity before assertions/simulation run.
    Other profiles are untouched.
    """
    if os.environ.get('SIM_V2_PROFILE') != 'arch-repaired-v113-evolution-single-2k-240s':
        return
    runpy.run_path(str(ROOT / 'apply_arch_v112_payment_repair.py'), run_name='__main__')
    runpy.run_path(str(ROOT / 'apply_arch_v113_payment_scope_fix.py'), run_name='__main__')


def main():
    prepare_profile_pilot()
    header, base_cards = parse(BASE.read_text())
    f10 = mutate(base_cards, F10_CUTS, F10_ADDS, 'F10_BASE')
    for key, (cuts, adds) in SPECS.items():
        cards = mutate(f10, cuts, adds, key)
        h = list(header)
        h[1] = f'Name=Kinnan Expanded Architecture {key}'
        path = DECKS / f'Kinnan_ARCH_{key}.dck'
        path.write_text('\n'.join(h + [f'1 {card}' for card in cards]) + '\n')
        print(key, 'CHANGES', len(cuts), 'CUT', cuts, 'ADD', adds)


if __name__ == '__main__':
    main()