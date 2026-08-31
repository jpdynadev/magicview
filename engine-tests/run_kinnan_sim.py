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


def _arg_value(args: list[str], name: str, default: str) -> str:
    try:
        index = args.index(name)
    except ValueError:
        return default
    return args[index + 1] if index + 1 < len(args) else default


def _live_runner(forwarded: list[str]):
    """Load the same runner the canonical full-99 worker would use.

    This is deliberately checked before Forge starts. When production parity is
    eventually flipped green, an accidentally retained v8/architecture runner
    must still fail rather than silently becoming the new production path.
    """
    mode = _arg_value(forwarded, "--mode", "screen")
    if mode == "adversarial":
        import manabrew_pilot_arch_adv as config
    else:
        import manabrew_pilot_arch as config
    return config.runner


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

    forwarded = list(args.worker_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]

    # Two independent barriers are intentional:
    # 1) the semantic/anchor/telemetry production manifest must be green;
    # 2) the actual live runner selected by the worker must identify as v9.
    # Today barrier (1) fails, so importing the legacy runner is avoided. Once
    # (1) becomes green, barrier (2) prevents a stale worker composition from
    # ever producing ranking evidence.
    assert_ranking_ready()
    assert_ranking_ready(runner=_live_runner(forwarded))
    return _run_module_path(WORKERS["ranking"], forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
