#!/usr/bin/env python3
"""Compose architecture-aware Kinnan policy with adversarial opponent policy."""
from __future__ import annotations

from typing import Any

import manabrew_pilot_v91_adversarial as adversarial  # installs pod/deck/keep/target policy first
import manabrew_pilot_arch as arch
import manabrew_pilot_v8 as runner

# Cache/pilot identity must follow the repaired architecture policy actually in
# use. v1.10 also breaks a pathological Forge replacement loop by declining a
# repeated identical Mockingbird replacement prompt after first allowing the
# normal policy decision. This is intentionally scoped to the exact same
# visible state so normal, resolvable copy choices are unchanged.
runner.PILOT_VERSION = 'arch-aware-v1.10-adversarial'

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

# Forge can re-advertise an optional replacement boolean without changing the
# visible state when the accepted `true` branch has no resolvable follow-up.
# The generic policy quite reasonably says yes to prompts containing "copy",
# which previously made Blue Farm's Mockingbird repeat the same prompt thousands
# of times, fill the JVM heap, and eventually close harness stdout. Preserve the
# first normal answer; only if the exact Mockingbird prompt repeats in the exact
# same visible state do we decline the replacement so Forge can continue.
_ARCH_ADV_RESPONSE = runner.base.response_for
_MOCKINGBIRD_BOOLEAN_STATES: set[tuple[int, str, str]] = set()


def repaired_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    inp = prompt.get('input') or {}
    if inp.get('type') == 'chooseBoolean':
        title = str((inp.get('presentation') or {}).get('title') or '')
        if 'apply replacement effect of mockingbird?' in title.lower():
            key = (player, arch.policy.visible_state_hash(snapshot), title)
            if key in _MOCKINGBIRD_BOOLEAN_STATES:
                return {
                    'type': 'chooseBoolean',
                    'output': {'type': 'decision', 'value': False},
                }
            _MOCKINGBIRD_BOOLEAN_STATES.add(key)
    return _ARCH_ADV_RESPONSE(prompt, snapshot, deck, player)


runner.base.response_for = repaired_response
arch.base.response_for = repaired_response

if __name__ == '__main__':
    raise SystemExit(runner.main())
