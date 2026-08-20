#!/usr/bin/env python3
"""Compose architecture-aware Kinnan policy with adversarial opponent policy."""
from __future__ import annotations

from typing import Any

import manabrew_pilot_v91_adversarial as adversarial  # installs pod/deck/keep/target policy first
import manabrew_pilot_arch as arch
import manabrew_pilot_v8 as runner

runner.PILOT_VERSION = 'arch-aware-v1.3-adversarial'

# Importing the architecture overlay intentionally replaces base.action_score so
# Kinnan can understand copy cards/Mirage Mirror. Re-compose the scorer here so
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
