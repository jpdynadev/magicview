#!/usr/bin/env python3
from pathlib import Path
import manabrew_pilot_v89
import manabrew_pilot_v8 as runner

runner.PILOT_VERSION = "v9.0.0"
deck_dir = Path(__file__).resolve().parent / "decks"
for deck_path in sorted(deck_dir.glob("Kinnan_M2K*.dck")):
    key = deck_path.stem.replace("Kinnan_", "", 1)
    runner.VARIANT_FILES[key] = deck_path.name

if __name__ == "__main__":
    raise SystemExit(runner.main())
