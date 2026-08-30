#!/usr/bin/env python3
"""Patch architecture pilot v1.15 with a bounded Replicate chooseNumber response.

Forge exposes Consign to Memory's Replicate prompt with an effectively unbounded
integer maximum.  The generic pilot chose that raw maximum (2^31-1), which
stranded the engine on deterministic idle-timeout paths.  v1.16 chooses a
conservative amount bounded by currently floating mana and otherwise 0. Forge
remains the legality/payment authority.
"""
from pathlib import Path

path = Path('engine-tests/manabrew_pilot_arch_adv.py')
text = path.read_text()
text = text.replace("runner.PILOT_VERSION = 'arch-aware-v1.15-adversarial'", "runner.PILOT_VERSION = 'arch-aware-v1.16-adversarial'")
text = text.replace("runner.PILOT_VERSION = 'arch-aware-v1.11-adversarial'", "runner.PILOT_VERSION = 'arch-aware-v1.16-adversarial'")
needle = """def repaired_response(\n    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int\n) -> dict[str, Any] | None:\n    inp = prompt.get('input') or {}\n"""
replacement = """def repaired_response(\n    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int\n) -> dict[str, Any] | None:\n    inp = prompt.get('input') or {}\n    if deck == 'Kinnan' and inp.get('type') == 'chooseNumber':\n        title = str((inp.get('presentation') or {}).get('title') or '')\n        if 'replicate' in title.lower():\n            lo = int(inp.get('min', inp.get('minimum', 0)) or 0)\n            hi_raw = int(inp.get('max', inp.get('maximum', lo)) or lo)\n            # Replicate {1}: after the base spell is cast, each extra copy costs\n            # one additional generic mana.  Use only authoritative floating mana\n            # as a conservative bound; Forge still validates the actual payment.\n            affordable = max(0, _player_mana_pool_total(snapshot, player))\n            chosen = max(lo, min(hi_raw, affordable))\n            return {\n                'type': 'chooseNumber',\n                'output': {'type': 'numberDecision', 'chosenNumber': chosen},\n            }\n"""
if needle not in text:
    raise SystemExit('repaired_response anchor not found')
text = text.replace(needle, replacement, 1)
path.write_text(text)
print('applied arch-aware-v1.16-adversarial replicate number fix')
