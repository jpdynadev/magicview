#!/usr/bin/env python3
"""Canonical launcher for every forward Kinnan simulation run.

Do not call sim_v2_worker*.py or historical manabrew_pilot_v*.py directly from
new workflows. This launcher owns execution-path identity and parity preflight.
Ranking remains blocked until pilot-v9 is production integrated.
"""
from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kinnan_execution_path import (  # noqa: E402
    CANONICAL_EXECUTION_PATH,
    EXECUTION_PATH_ENV,
    assert_component_ready,
    assert_ranking_ready,
)

WORKERS = {
    # Full-99 v3 is the only forward ranking worker. It composes the repaired
    # lifecycle, strict worker, card telemetry and v3 sidecar in one path.
    "ranking": HERE / "sim_v2_worker_arch_v152_full99.py",
}


def _run_module_path(path: Path, forwarded: list[str]) -> int:
    old_argv = sys.argv
    try:
        sys.argv = [str(path), *forwarded]
        namespace = runpy.run_path(str(path), run_name="__kinnan_canonical_worker__")
        main = namespace.get("main")
        if main is None:
            raise RuntimeError(f"worker has no main(): {path}")
        return int(main())
    finally:
        sys.argv = old_argv


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Canonical pilot-v9 Kinnan simulation launcher",
        add_help=True,
    )
    parser.add_argument(
        "--purpose",
        choices=("component-canary", "ranking"),
        default="ranking",
        help="component-canary validates semantics only; ranking requires full production parity",
    )
    parser.add_argument(
        "worker_args",
        nargs=argparse.REMAINDER,
        help="arguments after -- are forwarded to the canonical worker",
    )
    args = parser.parse_args()

    # The launcher, not individual workflows, owns path identity.
    os.environ[EXECUTION_PATH_ENV] = CANONICAL_EXECUTION_PATH

    if args.purpose == "component-canary":
        assert_component_ready()
        os.environ.setdefault("KINNAN_V9_ALLOW_CANARY", "1")
        import manabrew_pilot_v9

        return int(manabrew_pilot_v9.canary_main())

    # This intentionally fails today. It is the one gate that will open after
    # live Forge integration, exact anchors, replay and full-99 v3 all clear.
    assert_ranking_ready()
    forwarded = list(args.worker_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    return _run_module_path(WORKERS["ranking"], forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
