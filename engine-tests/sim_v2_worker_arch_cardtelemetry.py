#!/usr/bin/env python3
"""Architecture worker with read-only card telemetry sidecars.

The simulation result remains the normal compact sim-v2 record.  Rich telemetry
is written separately so it cannot affect cache/promotion schemas and can be
aggregated into card-level statistics after the game shards finish.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import sim_v2_worker_arch as arch


def _strict_pt4(result):
    turn = result.get("firstAttemptTurn")
    certified = bool(
        result.get("certifiedDeterministicAttempt")
        or (result.get("deterministicT4") and turn is not None and int(turn) <= 4)
    )
    return bool(result.get("protectedAttempt")) and certified and turn is not None and int(turn) <= 4


def main() -> int:
    mode = arch.ultra._arg_value("--mode", "screen")
    if mode == "adversarial":
        import manabrew_pilot_arch_adv as config
    else:
        import manabrew_pilot_arch as config

    from card_telemetry_v1 import install
    install(config.runner)

    outdir = Path(os.getenv("CARD_TELEMETRY_DIR", "out/card-telemetry"))
    outdir.mkdir(parents=True, exist_ok=True)
    original_run = config.runner.run_game

    def sidecar_run(*args, **kwargs):
        result = original_run(*args, **kwargs)
        telemetry = result.get("cardTelemetry") or {}
        if telemetry:
            variant = str(result.get("variant") or arch.ultra._arg_value("--variant", "unknown"))
            seed = int(result.get("seed") or 0)
            seat = int(result.get("kinnanSeat") or 0)
            pod = os.getenv("CEDH_POD", "balanced") if mode == "adversarial" else "screen"
            payload = {
                "schema": "kinnan-card-telemetry-v1",
                "pilotVersion": result.get("pilotVersion"),
                "variant": variant,
                "variantDeckSha256": result.get("variantDeckSha256"),
                "seed": seed,
                "kinnanSeat": seat,
                "podProfile": pod,
                "status": result.get("status"),
                "kinnanWon": bool(result.get("kinnanWon")),
                "winnerSeat": result.get("winnerSeat"),
                "firstAssemblyTurn": result.get("firstAssemblyTurn"),
                "firstAttemptTurn": result.get("firstAttemptTurn"),
                "certifiedDeterministicAttempt": bool(result.get("certifiedDeterministicAttempt")),
                "deterministicT4": bool(result.get("deterministicT4")),
                "protectedAttempt": bool(result.get("protectedAttempt")),
                "strictProtectedT4": _strict_pt4(result),
                "attemptResolved": bool(result.get("attemptResolved")),
                "comboLine": result.get("comboLine"),
                "primaryFailureCode": result.get("primaryFailureCode"),
                "mulligans": (result.get("mulligans") or {}).get(str(seat)),
                "protectionAvailable": result.get("protectionAvailable") or [],
                "telemetry": telemetry,
            }
            path = outdir / f"{variant}-s{seat}-seed{seed}-{pod}.json"
            path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
        return result

    config.runner.run_game = sidecar_run
    return arch.main()


if __name__ == "__main__":
    raise SystemExit(main())
