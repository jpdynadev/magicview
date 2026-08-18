#!/usr/bin/env python3
"""Architecture-aware sim-v2 worker.

Uses the architecture policy/decks while retaining sim-v2 cache identity,
exposure tracking, compact records, and session cleanup. Production workflows
must still request jvm-reuse=1 until the persistent equivalence gate clears.
"""
from __future__ import annotations

import json
import os

import sim_v2_worker_ultra as ultra


def main() -> int:
    os.environ.setdefault("SIM_V2_PROFILE", "arch-cold-v1")
    mode = ultra._arg_value("--mode", "screen")
    variant = ultra._arg_value("--variant", "")

    if mode == "adversarial":
        import manabrew_pilot_arch_adv as config
    else:
        import manabrew_pilot_arch as config

    runner = config.runner
    if variant not in runner.VARIANT_FILES:
        raise SystemExit(f"unknown architecture variant {variant}; known={sorted(runner.VARIANT_FILES)}")

    runner._SIM_V2_HOTPATCH_META = {
        "earlySuccess": False,
        "exactDeadline": False,
        "traceEnabled": True,
        "metricWrapperPreserved": True,
        "optimizedSource": None,
        "sessionLifecycle": "abort+reset",
        "policy": "architecture-aware",
    }

    requested_exposure = ultra._arg_values("--exposure-card")
    deck_path = runner.base.DECK_DIR / runner.VARIANT_FILES[variant]
    observation_universe = sorted(set(ultra._deck_card_names(deck_path)) | set(requested_exposure))
    ultra._install_observation_tracker(runner, observation_universe)
    ultra._install_session_lifecycle(runner)
    print(
        "SIM_V2_ARCH_CONFIG "
        + json.dumps({**runner._SIM_V2_HOTPATCH_META, "variant": variant, "observationUniverse": len(observation_universe)}, sort_keys=True),
        flush=True,
    )

    import sim_v2_worker
    original_compact = sim_v2_worker.compact_result

    def compact_with_events(result, cards):
        item = original_compact(result, cards)
        observed = set(result.get("v2ObservedCards") or [])
        observed.update(item.get("observedCards") or [])
        requested = set(cards)
        exposed = sorted(observed & requested)
        events = result.get("v2ObservationEvents") or []
        item["observedCards"] = sorted(observed)
        item["observedCardEvents"] = events
        item["exposureCards"] = exposed
        item["slotExposed"] = bool(exposed)
        item["exposureEvents"] = [event for event in events if event.get("card") in requested]
        item["v2EarlyExit"] = False
        item["v2DeadlineExit"] = False
        item["v2SessionCleanup"] = bool(result.get("v2SessionCleanup"))
        item["v2SessionCleanupError"] = result.get("v2SessionCleanupError")
        return item

    sim_v2_worker.compact_result = compact_with_events
    return sim_v2_worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
