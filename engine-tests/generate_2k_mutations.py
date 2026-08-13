#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECKS = ROOT / "decks"
SOURCE = DECKS / "Kinnan_TestB.dck"
MANIFEST = ROOT / "mutation-2k-manifest.json"

# Candidate additions are Simic/colorless cards with established relevance to
# Kinnan shells or cards already exercised by this repository's B2/M25 work.
ADD_POOL = [
    "Clever Impersonator",
    "Consecrated Sphinx",
    "Wan Shi Tong, Librarian",
    "The One Ring",
    "Tidespout Tyrant",
    "Spellseeker",
    "Tribute Mage",
    "Trinket Mage",
    "Noble Hierarch",
    "Boreal Druid",
    "Arbor Elf",
    "Kiora's Follower",
    "Devoted Druid",
    "Biomancer's Familiar",
    "Training Grounds",
    "Freed from the Real",
    "Pemmin's Aura",
    "Reshape",
    "Green Sun's Zenith",
    "Eldritch Evolution",
    "Merchant Scroll",
    "Personal Tutor",
    "Mana Drain",
    "Delay",
    "Spell Pierce",
    "Miscast",
    "Strix Serenade",
    "Autumn's Veil",
    "Spellskite",
    "Haywire Mite",
    "Pollywog Prodigy",
    "Ledger Shredder",
]

# Preserve the core deterministic engine, premium acceleration and the mana base
# in the broad screen. Mutate flex creatures, interaction, tutors and engines.
CUT_POOL = [
    "Goblin Cannon",
    "Drift of Phantasms",
    "Endurance",
    "Enduring Vitality",
    "Faerie Mastermind",
    "Hullbreaker Horror",
    "Hydroelectric Specimen",
    "Mockingbird",
    "Prophet of Distortion",
    "Seedborn Muse",
    "Trophy Mage",
    "Valley Floodcaller",
    "Dispel",
    "Defense Grid",
    "Energy Refractor",
    "Fellwar Stone",
    "Moonsilver Key",
    "Springleaf Drum",
    "Talisman of Curiosity",
    "Mystic Remora",
    "Rhystic Study",
    "Sylvan Library",
    "An Offer You Can't Refuse",
    "Borne Upon a Wind",
    "Chain of Vapor",
    "Chord of Calling",
    "Crop Rotation",
    "Flusterstorm",
    "Force of Negation",
    "Force of Vigor",
    "Into the Flood Maw",
    "Mental Misstep",
    "Mindbreak Trap",
    "Misdirection",
    "Muddle the Mixture",
    "Sink into Stupor",
    "Swan Song",
    "Veil of Summer",
    "Whir of Invention",
    "Worldly Tutor",
    "Fabricate",
    "Finale of Devastation",
    "Nature's Rhythm",
    "Neoform",
    "Summoner's Pact",
    "Transmute Artifact",
    "Invasion of Ikoria",
    "Tezzeret the Seeker",
]


def parse_main(text: str) -> tuple[list[str], list[str], list[str]]:
    before, rest = text.split("[Main]\n", 1)
    lines = rest.splitlines()
    cards = [line[2:] for line in lines if line.startswith("1 ")]
    return before, lines, cards


def replace_cards(source: str, cuts: tuple[str, ...], adds: tuple[str, ...], name: str) -> str:
    text = source.replace("Name=Kinnan M25 Prophet No Clever", f"Name=Kinnan {name}")
    for cut, add in zip(cuts, adds):
        needle = f"1 {cut}\n"
        if needle not in text:
            raise RuntimeError(f"missing cut slot: {cut}")
        text = text.replace(needle, f"1 {add}\n", 1)
    return text


def generate(count: int = 2000, seed: int = 20260813) -> list[dict[str, object]]:
    source = SOURCE.read_text()
    _, _, source_cards = parse_main(source)
    source_set = set(source_cards)
    cuts = [c for c in CUT_POOL if c in source_set]
    adds = [c for c in ADD_POOL if c not in source_set]
    if len(cuts) < 20 or len(adds) < 12:
        raise RuntimeError("mutation pools unexpectedly small")

    rng = random.Random(seed)
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    manifest: list[dict[str, object]] = []

    # Mix 1-, 2-, 3- and 4-card swaps. Bias toward small edits so attribution is
    # still possible while retaining enough combinatorial breadth for 2,000 lists.
    swap_sizes = [1] * 8 + [2] * 14 + [3] * 10 + [4] * 5
    attempts = 0
    while len(manifest) < count and attempts < count * 500:
        attempts += 1
        k = rng.choice(swap_sizes)
        chosen_cuts = tuple(sorted(rng.sample(cuts, k)))
        chosen_adds = tuple(sorted(rng.sample(adds, k)))
        key = (chosen_cuts, chosen_adds)
        if key in seen:
            continue
        seen.add(key)
        idx = len(manifest)
        variant = f"M2K{idx:04d}"
        deck_text = replace_cards(source, chosen_cuts, chosen_adds, variant)
        deck_path = DECKS / f"Kinnan_{variant}.dck"
        deck_path.write_text(deck_text)
        manifest.append({
            "index": idx,
            "variant": variant,
            "file": deck_path.name,
            "swapCount": k,
            "cuts": list(chosen_cuts),
            "adds": list(chosen_adds),
            "sha256": hashlib.sha256(deck_text.encode()).hexdigest(),
        })

    if len(manifest) != count:
        raise RuntimeError(f"generated {len(manifest)} of {count} requested mutations")
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--print-range", nargs=2, type=int, metavar=("START", "END"))
    args = parser.parse_args()
    manifest = generate(args.count, args.seed)
    if args.print_range:
        start, end = args.print_range
        for row in manifest[start:end]:
            print(row["variant"])
    else:
        print(json.dumps({"generated": len(manifest), "manifest": str(MANIFEST)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
