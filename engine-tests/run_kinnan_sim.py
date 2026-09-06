#!/usr/bin/env python3
"""Canonical launcher for every forward Kinnan simulation run.

Do not call sim_v2_worker*.py or historical manabrew_pilot_v*.py directly from
new workflows. This launcher owns execution-path identity and parity preflight.
Ranking remains blocked until pilot-v9 is production integrated.
"""
from __future__ import annotations

import argparse
import hashlib
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


def _pop_option(args: list[str], name: str) -> tuple[list[str], str | None]:
    forwarded = list(args)
    try:
        index = forwarded.index(name)
    except ValueError:
        return forwarded, None
    if index + 1 >= len(forwarded):
        raise RuntimeError(f"{name} requires a value")
    value = forwarded[index + 1]
    del forwarded[index:index + 2]
    return forwarded, value


def validate_submitted_deck(path: Path) -> tuple[str, list[str]]:
    """Validate the strict input boundary required by full-99 v3 telemetry."""
    section = ""
    commanders: list[str] = []
    main: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.lower()
            continue
        if section not in {"[commander]", "[main]"}:
            raise RuntimeError(f"{path}:{number}: card outside [Commander]/[Main]")
        try:
            count_text, name = line.split(" ", 1)
            count = int(count_text)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"{path}:{number}: expected '<count> <card name>'") from exc
        name = name.split("|", 1)[0].strip()
        if count <= 0 or not name:
            raise RuntimeError(f"{path}:{number}: invalid card row")
        target = commanders if section == "[commander]" else main
        target.extend([name] * count)
    if commanders != ["Kinnan, Bonder Prodigy"]:
        raise RuntimeError("submitted deck must have exactly one Kinnan, Bonder Prodigy commander")
    if len(main) != 99 or len(set(main)) != 99:
        raise RuntimeError("submitted deck must have exactly 99 unique main-deck cards")
    return hashlib.sha256(path.read_bytes()).hexdigest(), main


def _register_submitted_deck(runner, forwarded: list[str], deck_file: str | None) -> None:
    if deck_file is None:
        return
    variant = _arg_value(forwarded, "--variant", "")
    if not variant:
        raise RuntimeError("--deck-file requires --variant")
    path = Path(deck_file).resolve(strict=True)
    validate_submitted_deck(path)
    runner.VARIANT_FILES[variant] = str(path)


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


def _forwarded(worker_args: list[str]) -> list[str]:
    forwarded = list(worker_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    return forwarded


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
    forwarded = _forwarded(args.worker_args)
    forwarded, deck_file = _pop_option(forwarded, "--deck-file")

    if args.purpose == "component-canary":
        assert_component_ready()
        os.environ.setdefault("KINNAN_V9_ALLOW_CANARY", "1")
        if forwarded:
            if forwarded[0] == "--live-forge":
                return _run_module_path(HERE / "kinnan_v9_forge_canary.py", forwarded[1:])
            if forwarded[0] == "--production-parity":
                return _run_module_path(
                    HERE / "kinnan_v9_production_parity_canary.py", forwarded[1:]
                )
            raise RuntimeError(
                "component canary arguments must begin with --live-forge or "
                "--production-parity; ranking workers are not available through the canary path"
            )
        import manabrew_pilot_v9

        return int(manabrew_pilot_v9.canary_main())

    # Two independent barriers are intentional:
    # 1) the semantic/anchor/telemetry production manifest must be green;
    # 2) the actual live runner selected by the worker must identify as v9.
    # Today barrier (1) fails, so importing the legacy runner is avoided. Once
    # (1) becomes green, barrier (2) prevents a stale worker composition from
    # ever producing ranking evidence.
    assert_ranking_ready()
    live_runner = _live_runner(forwarded)
    _register_submitted_deck(live_runner, forwarded, deck_file)
    assert_ranking_ready(runner=live_runner)
    return _run_module_path(WORKERS["ranking"], forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
