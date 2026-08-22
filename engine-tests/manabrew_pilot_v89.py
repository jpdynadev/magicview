#!/usr/bin/env python3
"""v8.9 experiment wrapper: mutation registration and clearer conversion endpoints."""
from __future__ import annotations
import sys
import manabrew_pilot_v88 as v88  # applies protocol compatibility patch
import manabrew_pilot_v8 as v8

v8.PILOT_VERSION = "v8.9.0"
v8.VARIANT_FILES.update({
    "M25C1": "Kinnan_M25C1.dck",
    "M25C2": "Kinnan_M25C2.dck",
    "M25C3": "Kinnan_M25C3.dck",
    "M25C4": "Kinnan_M25C4.dck",
    "M25C5": "Kinnan_M25C5.dck",
    "M25C6": "Kinnan_M25C6.dck",
})

_original_run_game = v8.run_game

def run_game(*args, **kwargs):
    result = _original_run_game(*args, **kwargs)
    attempt_turn = result.get("firstAttemptTurn")
    result["certifiedDeterministicAttempt"] = bool(
        result.get("deterministicT4") and attempt_turn is not None and attempt_turn <= 4
    )
    # Preserve natural Forge game-over as a separate, stricter endpoint.
    result["naturalWinAfterAttempt"] = bool(result.get("attemptResolved"))
    result["attemptResolved"] = result["certifiedDeterministicAttempt"]
    return result

v8.run_game = run_game

if __name__ == "__main__":
    raise SystemExit(v8.main())
