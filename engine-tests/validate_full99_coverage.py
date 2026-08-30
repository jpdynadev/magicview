#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

VALID = {"game_over", "horizon_complete"}
SCHEMA = "kinnan-full99-card-telemetry-v2"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    games = []
    for pattern in args.paths:
        for path in glob.glob(pattern, recursive=True):
            value = json.loads(Path(path).read_text())
            games.extend(value if isinstance(value, list) else [value])
    valid = [g for g in games if g.get("status") in VALID]
    failures = []
    for game in valid:
        rows = game.get("cardTelemetryRows") or []
        names = [r.get("card") for r in rows]
        missing_schema = [r.get("card") for r in rows if r.get("schemaVersion") != SCHEMA]
        missing_engine = [r.get("card") for r in rows if not r.get("engineId")]
        if len(rows) != 99 or len(set(names)) != 99 or missing_schema or missing_engine or not game.get("engineId"):
            failures.append({
                "key": [game.get("variant"), game.get("seed"), game.get("kinnanSeat"), game.get("podProfile")],
                "rows": len(rows), "distinct": len(set(names)),
                "duplicates": sorted({n for n in names if names.count(n) > 1}),
                "schemaMismatches": missing_schema,
                "missingEngineId": missing_engine,
            })
    report = {
        "schemaVersion": SCHEMA,
        "validGames": len(valid),
        "expectedRows": len(valid) * 99,
        "actualRows": sum(len(g.get("cardTelemetryRows") or []) for g in valid),
        "missingCards": sum(max(0, 99 - len(set(r.get("card") for r in (g.get("cardTelemetryRows") or [])))) for g in valid),
        "duplicateGames": failures,
        "coverageValid": bool(valid) and not failures,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["coverageValid"] or report["actualRows"] != report["expectedRows"]:
        raise SystemExit("full-99 telemetry coverage failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
