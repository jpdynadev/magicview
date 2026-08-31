#!/usr/bin/env python3
"""v1.42 lifecycle plus opt-in complete-99 telemetry sidecars."""
from __future__ import annotations

import os
from pathlib import Path

import sim_v2_worker_ultra as ultra
import sim_v2_worker_arch_v142  # installs the repaired one-JVM lifecycle hook
import sim_v2_worker_arch as arch


def main() -> int:
    mode = ultra._arg_value("--mode", "screen")
    variant = ultra._arg_value("--variant", "")
    if mode == "adversarial":
        import manabrew_pilot_arch_adv as config
    else:
        import manabrew_pilot_arch as config

    from card_telemetry_v1 import install
    from full99_telemetry_v2 import attach
    from full99_telemetry_v3_bridge import attach_v3
    install(config.runner)

    import sim_v2_worker
    original = sim_v2_worker.compact_result
    deck_path = Path(config.runner.base.DECK_DIR) / config.runner.VARIANT_FILES[variant]
    engine_id = ultra._arg_value("--engine-id", "")

    def compact_full99(result, exposure_cards):
        item = original(result, exposure_cards)
        item["podProfile"] = os.getenv("CEDH_POD", "balanced") if mode == "adversarial" else "screen"
        item["engineId"] = engine_id
        return attach_v3(attach(item, result, deck_path), result, deck_path)

    sim_v2_worker.compact_result = compact_full99
    return arch.main()


if __name__ == "__main__":
    raise SystemExit(main())
