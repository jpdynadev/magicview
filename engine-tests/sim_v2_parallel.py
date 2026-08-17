#!/usr/bin/env python3
"""Parallel shard launcher for sim-v2.

Splits one canonical seed shard across N local worker processes.  Each child owns
its own persistent Forge JVM, so no RPC streams are shared across processes.  The
merged output is sorted back into canonical seed order for deterministic pairing.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("harness_jar")
    ap.add_argument("forge_home")
    ap.add_argument("--mode", choices=("screen", "adversarial"), required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--fixed-seat", type=int, required=True)
    ap.add_argument("--seeds", nargs="+", type=int, required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-round", type=int, default=4)
    ap.add_argument("--max-prompts", type=int, default=3000)
    ap.add_argument("--max-seconds", type=int, default=75)
    ap.add_argument("--jvm-reuse", type=int, default=8)
    ap.add_argument("--xmx", default="1280m")
    ap.add_argument("--xms", default="192m")
    ap.add_argument("--cache-dir", default=".sim-cache/v2")
    ap.add_argument("--output", required=True)
    ap.add_argument("--engine-id", default=os.getenv("MANABREW_REF", "unknown-engine"))
    ap.add_argument("--exposure-card", action="append", default=[])
    ap.add_argument("--retain-traces", choices=("none", "failures", "all"), default="failures")
    ap.add_argument("--audit-every", type=int, default=200)
    args = ap.parse_args()

    worker_count = max(1, min(args.workers, len(args.seeds)))
    buckets = [[] for _ in range(worker_count)]
    for i, seed in enumerate(args.seeds):
        buckets[i % worker_count].append(seed)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.parent / (out.stem + ".parts")
    tmp.mkdir(parents=True, exist_ok=True)

    procs: list[tuple[subprocess.Popen[str], Path, Path, list[int]]] = []
    started = time.monotonic()
    for idx, seeds in enumerate(buckets):
        part = tmp / f"part-{idx}.json"
        log = tmp / f"part-{idx}.log"
        child_cache = Path(args.cache_dir) / f"worker-{idx}"
        cmd = [
            sys.executable,
            str(HERE / "sim_v2_worker_ultra.py"),
            args.harness_jar,
            args.forge_home,
            "--mode", args.mode,
            "--variant", args.variant,
            "--fixed-seat", str(args.fixed_seat),
            "--seeds", *[str(s) for s in seeds],
            "--max-round", str(args.max_round),
            "--max-prompts", str(args.max_prompts),
            "--max-seconds", str(args.max_seconds),
            "--jvm-reuse", str(args.jvm_reuse),
            "--xmx", args.xmx,
            "--xms", args.xms,
            "--cache-dir", str(child_cache),
            "--output", str(part),
            "--engine-id", args.engine_id,
            "--retain-traces", args.retain_traces,
            "--audit-every", str(args.audit_every),
        ]
        for card in args.exposure_card:
            cmd.extend(["--exposure-card", card])
        fh = log.open("w")
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, text=True)
        proc._sim_v2_log_handle = fh  # type: ignore[attr-defined]
        procs.append((proc, part, log, seeds))

    failures = []
    for proc, part, log, seeds in procs:
        rc = proc.wait()
        getattr(proc, "_sim_v2_log_handle").close()
        if rc != 0 or not part.exists():
            failures.append({"rc": rc, "log": str(log), "seeds": seeds})

    if failures:
        print(json.dumps({"parallelWorkerFailures": failures}, indent=2), file=sys.stderr)
        for failure in failures:
            try:
                print(Path(failure["log"]).read_text()[-8000:], file=sys.stderr)
            except Exception:
                pass
        return 2

    merged = []
    for _, part, _, _ in procs:
        payload = json.loads(part.read_text())
        if not isinstance(payload, list):
            raise SystemExit(f"non-list worker output {part}")
        merged.extend(payload)
    merged.sort(key=lambda g: (int(g.get("seed", -1)), int(g.get("kinnanSeat", -1))))
    expected = sorted(args.seeds)
    actual = sorted(int(g.get("seed")) for g in merged)
    if actual != expected:
        raise SystemExit(f"seed mismatch expected={expected} actual={actual}")
    out.write_text(json.dumps(merged, indent=2))

    summaries = []
    for _, _, log, _ in procs:
        for line in log.read_text().splitlines():
            if line.startswith("SIM_V2_SUMMARY "):
                try:
                    summaries.append(json.loads(line.split(" ", 1)[1]))
                except Exception:
                    pass
    summary = {
        "variant": args.variant,
        "mode": args.mode,
        "seat": args.fixed_seat,
        "games": len(merged),
        "workers": worker_count,
        "cacheHits": sum(int(s.get("cacheHits", 0)) for s in summaries),
        "jvmStarts": sum(int(s.get("jvmStarts", 0)) for s in summaries),
        "childWallMs": sum(int(s.get("wallMs", 0)) for s in summaries),
        "outerWallMs": round((time.monotonic() - started) * 1000),
        "strictProtectedT4": sum(bool(g.get("strictProtectedT4")) for g in merged),
        "errors": sum(g.get("status") not in {"game_over", "horizon_complete"} for g in merged),
    }
    print("SIM_V2_PARALLEL_SUMMARY " + json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
