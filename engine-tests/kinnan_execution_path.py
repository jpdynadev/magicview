#!/usr/bin/env python3
"""Single source of truth for Kinnan simulation execution.

All *new* simulation/screen/confirmation work must enter through this module.
Historical runners remain in the repository as reproducibility fixtures only;
they are not valid production-ranking entrypoints.

The contract is intentionally fail closed:
- the requested execution path must be ``pilot-v9``;
- component/canary work may run once v9 component parity is valid;
- ranking work additionally requires the production parity manifest to pass;
- a live ranking runner must identify itself as a v9 runner.

This lets us cleanly preserve old experiment code without allowing a future
workflow or scheduler to silently fall back to the old architecture/v8 pilot.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CANONICAL_EXECUTION_PATH = "pilot-v9"
EXECUTION_PATH_ENV = "KINNAN_EXECUTION_PATH"
MANIFEST_PATH = HERE / "kinnan_policy_parity_manifest_v2.json"


class ExecutionPathError(RuntimeError):
    """Raised when a Kinnan run would bypass the canonical v9 path."""


def requested_execution_path() -> str:
    return str(os.getenv(EXECUTION_PATH_ENV, "")).strip()


def assert_canonical_path() -> None:
    requested = requested_execution_path()
    if requested != CANONICAL_EXECUTION_PATH:
        raise ExecutionPathError(
            "Kinnan simulation execution is centralized on pilot-v9. "
            f"Set {EXECUTION_PATH_ENV}={CANONICAL_EXECUTION_PATH!s} and use "
            "engine-tests/run_kinnan_sim.py; legacy direct runners are archived only."
        )


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text())


def component_parity_report() -> dict[str, Any]:
    from validate_kinnan_policy_parity_v2 import validate

    return validate(_load_manifest(), component_only=True)


def production_parity_report() -> dict[str, Any]:
    from validate_kinnan_policy_parity_v2 import validate

    return validate(_load_manifest(), component_only=False)


def assert_component_ready() -> None:
    assert_canonical_path()
    report = component_parity_report()
    if not report.get("valid"):
        raise ExecutionPathError(
            "pilot-v9 component parity failed: " + "; ".join(report.get("failures") or [])
        )


def assert_ranking_ready(*, runner: Any | None = None) -> None:
    """Require every gate needed before a result can enter ranking evidence."""
    assert_canonical_path()

    # Keep the pilot's own fail-closed assertion in the chain as well as the
    # manifest validator so one cannot accidentally drift from the other.
    import manabrew_pilot_v9 as pilot_v9

    report = production_parity_report()
    if not report.get("valid"):
        raise ExecutionPathError(
            "pilot-v9 production parity is not ready: "
            + "; ".join(report.get("failures") or [])
        )
    pilot_v9.assert_ranking_ready()

    if runner is not None:
        version = str(getattr(runner, "PILOT_VERSION", ""))
        if not version.startswith("v9"):
            raise ExecutionPathError(
                "ranking runner is not pilot-v9: "
                f"loaded PILOT_VERSION={version!r}. Legacy runner execution is blocked."
            )


def describe() -> dict[str, Any]:
    component = component_parity_report()
    production = production_parity_report()
    return {
        "canonicalExecutionPath": CANONICAL_EXECUTION_PATH,
        "requestedExecutionPath": requested_execution_path(),
        "componentReady": bool(component.get("valid")),
        "productionRankingReady": bool(production.get("valid")),
        "componentFailures": component.get("failures") or [],
        "productionFailures": production.get("failures") or [],
    }


def main() -> int:
    try:
        assert_component_ready()
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc), **describe()}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, **describe()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
