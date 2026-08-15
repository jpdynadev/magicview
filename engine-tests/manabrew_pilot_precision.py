#!/usr/bin/env python3
from pathlib import Path
import manabrew_pilot_v89
import manabrew_pilot_v8 as runner

runner.PILOT_VERSION='precision-f10-v1'
deck_dir=Path(__file__).resolve().parent/'decks'
for p in sorted(deck_dir.glob('Kinnan_PREC_*.dck')):
    key=p.stem.replace('Kinnan_PREC_','',1)
    runner.VARIANT_FILES[key]=p.name

if __name__=='__main__':
    raise SystemExit(runner.main())
