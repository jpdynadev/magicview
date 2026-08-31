#!/usr/bin/env python3
"""Reject newly introduced Kinnan simulation paths that bypass pilot-v9.

Historical workflows are intentionally retained as immutable experiment
records. The migration boundary is enforced on *changed/new* workflow files:
once a Kinnan workflow is touched after this cleanup, any simulation command in
it must use ``engine-tests/run_kinnan_sim.py``. This prevents legacy execution
from creeping back in without rewriting old evidence-producing YAML.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"
CANONICAL = "engine-tests/run_kinnan_sim.py"

# Match actual Python execution commands only. Bare path mentions in workflow
# triggers, artifact lists, comments, or documentation are not execution paths.
LEGACY_EXECUTION = re.compile(
    r"python(?:3)?\s+engine-tests/(?:"
    r"sim_v2_worker[^\s]*\.py|"
    r"manabrew_pilot_v[0-8](?:\.[0-9]+)?[^\s]*\.py"
    r")"
)


def changed_paths(before: str, head: str) -> list[Path]:
    if not before or set(before) == {"0"}:
        return []
    proc = subprocess.run(
        ["git", "diff", "--name-only", before, head, "--", ".github/workflows"],
        cwd=ROOT,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [ROOT / line.strip() for line in proc.stdout.splitlines() if line.strip()]


def audit(paths: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in paths:
        if not path.exists() or path.parent != WORKFLOW_DIR:
            continue
        if not path.name.startswith("kinnan"):
            continue
        text = path.read_text()
        legacy = sorted(set(LEGACY_EXECUTION.findall(text)))
        if legacy and CANONICAL not in text:
            failures.append(
                f"{path.relative_to(ROOT)}: direct legacy simulation command(s) found; "
                f"route through {CANONICAL}"
            )
        if CANONICAL in text and legacy:
            failures.append(
                f"{path.relative_to(ROOT)}: mixes canonical and legacy simulation commands"
            )
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default="")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--path", action="append", default=[])
    args = ap.parse_args()

    if args.path:
        paths = [ROOT / p for p in args.path]
    else:
        paths = changed_paths(args.before, args.head)

    failures = audit(paths)
    if failures:
        print("KINNAN_EXECUTION_PATH_AUDIT_FAILED")
        for failure in failures:
            print(" - " + failure)
        return 1
    print(f"KINNAN_EXECUTION_PATH_AUDIT_OK checked={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
