#!/usr/bin/env python3
from pathlib import Path
import manabrew_pilot_v89
import manabrew_pilot_v8 as runner

runner.PILOT_VERSION = 'lever-v1'
deck_dir = Path(__file__).resolve().parent / 'decks'
runner.VARIANT_FILES['DORKMAX'] = 'Kinnan_LEVER_DORKMAX.dck'
runner.VARIANT_FILES['TUTORMAX'] = 'Kinnan_LEVER_TUTORMAX.dck'
runner.VARIANT_FILES['MESHMAX'] = 'Kinnan_LEVER_MESHMAX.dck'

if __name__ == '__main__':
    raise SystemExit(runner.main())
