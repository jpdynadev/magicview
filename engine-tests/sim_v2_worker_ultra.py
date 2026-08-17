#!/usr/bin/env python3
"""Ultra entrypoint: validated v2 worker plus pilot hot-path optimizations."""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _arg_value(flag: str, default: str) -> str:
    try:
        i = sys.argv.index(flag)
        return sys.argv[i + 1]
    except (ValueError, IndexError):
        return default


def main() -> int:
    mode = _arg_value("--mode", "screen")
    if mode == "adversarial":
        import manabrew_pilot_precision_adv as config
    else:
        import manabrew_pilot_precision as config

    from sim_v2_hotpatch import install

    trace_enabled = os.getenv("SIM_V2_TRACE", "0").lower() in {"1", "true", "yes"}
    early_success = os.getenv("SIM_V2_EARLY_SUCCESS", "1").lower() not in {"0", "false", "no"}
    meta = install(config.runner, early_success=early_success, trace_enabled=trace_enabled)
    print("SIM_V2_HOTPATCH " + __import__("json").dumps(meta, sort_keys=True), flush=True)

    import sim_v2_worker

    return sim_v2_worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
