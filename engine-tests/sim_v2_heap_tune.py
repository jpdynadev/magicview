#!/usr/bin/env python3
"""Choose the smallest stable Forge heap on the current runner image.

The tuner uses a tiny canonical F10 micro-benchmark and never reuses result cache
between heap candidates.  It prefers the smallest heap that completes every game
without engine/pilot errors.  Among equally small stable candidates it records
wall time for observability, but memory safety wins over tiny speed differences.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPLETED = {"game_over", "horizon_complete"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("harness_jar")
    ap.add_argument("forge_home")
    ap.add_argument("--variant", default="P00_F10")
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--seed-base", type=int, default=2999000)
    ap.add_argument("--games", type=int, default=4)
    ap.add_argument("--heaps", nargs="+", default=["896m", "1024m", "1280m", "1536m", "2048m"])
    ap.add_argument("--output", required=True)
    ap.add_argument("--github-output")
    args = ap.parse_args()

    results = []
    selected = None
    seeds = [args.seed_base + i for i in range(args.games)]
    with tempfile.TemporaryDirectory(prefix="sim-v2-heap-") as td:
        root = Path(td)
        for heap in args.heaps:
            out = root / f"{heap}.json"
            cache = root / f"cache-{heap}"
            cmd = [
                sys.executable,
                str(HERE / "sim_v2_worker_ultra.py"),
                args.harness_jar,
                args.forge_home,
                "--mode", "screen",
                "--variant", args.variant,
                "--fixed-seat", str(args.seat),
                "--seeds", *[str(x) for x in seeds],
                "--max-round", "4",
                "--max-prompts", "3000",
                "--max-seconds", "75",
                "--jvm-reuse", str(args.games),
                "--xmx", heap,
                "--xms", "128m",
                "--cache-dir", str(cache),
                "--retain-traces", "none",
                "--audit-every", "0",
                "--output", str(out),
                "--engine-id", os.getenv("MANABREW_REF", "heap-tune"),
            ]
            started = time.monotonic()
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            elapsed = round((time.monotonic() - started) * 1000)
            payload = []
            if out.exists():
                try:
                    payload = json.loads(out.read_text())
                except Exception:
                    payload = []
            stable = (
                proc.returncode == 0
                and len(payload) == len(seeds)
                and all(g.get("status") in COMPLETED for g in payload)
            )
            row = {
                "heap": heap,
                "stable": stable,
                "rc": proc.returncode,
                "games": len(payload),
                "errors": sum(g.get("status") not in COMPLETED for g in payload),
                "wallMs": elapsed,
            }
            results.append(row)
            print("HEAP_CANDIDATE " + json.dumps(row, sort_keys=True), flush=True)
            if stable and selected is None:
                selected = heap
                # We deliberately stop at the first stable heap: the candidate
                # list is ascending, and lower memory allows more local workers.
                break

    if selected is None:
        selected = args.heaps[-1]
        status = "FALLBACK"
    else:
        status = "TUNED"
    report = {"selected": selected, "status": status, "candidates": results}
    Path(args.output).write_text(json.dumps(report, indent=2))
    github_output = args.github_output or os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"xmx={selected}\n")
            f.write(f"status={status}\n")
    print("HEAP_TUNE " + json.dumps(report, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
