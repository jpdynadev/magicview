#!/usr/bin/env python3
"""Compose architecture-aware Kinnan policy with adversarial opponent policy."""
from __future__ import annotations

from typing import Any

import manabrew_pilot_v91_adversarial as adversarial  # installs pod/deck/keep/target policy first
import manabrew_pilot_arch as arch
import manabrew_pilot_v8 as runner

# Cache/pilot identity must follow the repaired architecture policy actually in
# use. v1.9 consumes Manabrew's canonical `validColors` field and submits the
# exact offered token while matching it against W/U/B/R/G/C payment policy.
runner.PILOT_VERSION = 'arch-aware-v1.9-adversarial'

_COLOR_ALIASES = {
    'W': 'W', 'WHITE': 'W',
    'U': 'U', 'BLUE': 'U',
    'B': 'B', 'BLACK': 'B',
    'R': 'R', 'RED': 'R',
    'G': 'G', 'GREEN': 'G',
    'C': 'C', 'COLORLESS': 'C',
}


def choose_payment_color_exact(inp: dict[str, Any], preferred: list[str]) -> str:
    """Choose canonically, but submit the exact token Manabrew advertised.

    The canonical ChooseColorInput schema exposes the legal strings as
    `validColors`. Older pilot code looked only for `availableColors`/`colors`,
    so flexible sources such as Fellwar Stone could fall back to U/Blue even
    when that color was not one of Forge's legal options. Preserve the exact
    offered token while consuming the matching canonical preferred color.
    """
    raw_available = [
        str(item)
        for item in (
            inp.get('validColors')
            or inp.get('availableColors')
            or inp.get('colors')
            or []
        )
    ]
    canonical = [
        (raw, _COLOR_ALIASES.get(raw.strip().upper(), raw.strip().upper()))
        for raw in raw_available
    ]
    for pref in list(preferred):
        wanted = _COLOR_ALIASES.get(str(pref).strip().upper(), str(pref).strip().upper())
        for raw, offered in canonical:
            if offered == wanted:
                preferred.remove(pref)
                return raw
    if raw_available:
        return raw_available[0]
    return preferred.pop(0) if preferred else 'U'


# The v8 runner and architecture overlay share this module object, so this fixes
# adversarial chooseColor responses without changing Forge legality or screen-mode
# policy that already passed the production gate.
arch.policy.choose_payment_color = choose_payment_color_exact
runner.policy.choose_payment_color = choose_payment_color_exact

# Importing the architecture overlay intentionally replaces base.action_score so
# Kinnan can understand architecture cards. Re-compose the scorer here so
# non-Kinnan seats retain v9.1's race/disruption priorities in confirmation pods.
def composed_action_score(
    deck: str, action: dict[str, Any], snapshot: dict[str, Any], player: int
) -> int:
    if deck == 'Kinnan':
        return arch.action_score(deck, action, snapshot, player)
    return adversarial.adversarial_score(deck, action, snapshot, player)


arch.base.action_score = composed_action_score

if __name__ == '__main__':
    raise SystemExit(runner.main())
