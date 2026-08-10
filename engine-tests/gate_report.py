#!/usr/bin/env python3
"""Create a deliberately non-inferential report for the two-game engineering gate."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "engine-tests" / "results"
REPORT = RESULTS / "report"
REPORT.mkdir(parents=True, exist_ok=True)


def load_results() -> list[dict]:
    rows = []
    for path in sorted(RESULTS.glob("pilot-result-*.json")):
        row = json.loads(path.read_text())
        row["resultFile"] = path.name
        rows.append(row)
    return rows


def main() -> int:
    rows = load_results()
    complete_statuses = {"game_over", "horizon_complete"}
    complete = [row for row in rows if row.get("status") in complete_statuses]
    report = {
        "stage": "two-game-engineering-gate",
        "inferentialClaim": False,
        "expectedGames": 2,
        "observedGames": len(rows),
        "completedGames": len(complete),
        "gatePassed": len(rows) == 2 and len(complete) == 2,
        "engineErrors": sum(row.get("status") in {"crash", "unsupported_prompt"} for row in rows),
        "timeouts": sum(
            row.get("status")
            in {"idle_timeout", "stale_prompt_timeout", "wall_timeout", "prompt_cap", "round_cap"}
            for row in rows
        ),
        "games": rows,
    }
    (REPORT / "gate-report.json").write_text(json.dumps(report, indent=2))

    columns = [
        "variant",
        "seed",
        "kinnanSeat",
        "status",
        "winnerSeat",
        "kinnanWon",
        "deterministicT3",
        "deterministicT4",
        "firstAssemblyTurn",
        "firstAttemptTurn",
        "protectedAttempt",
        "attemptResolved",
        "primaryFailureCode",
        "prompts",
        "wallMs",
    ]
    with (REPORT / "games.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Kinnan Forge/Manabrew v8 engineering gate",
        "",
        "> This two-game run validates the controller/engine path. It is not a win-rate sample.",
        "",
        f"- Gate passed: **{report['gatePassed']}**",
        f"- Completed: **{len(complete)}/2**",
        f"- Engine/controller errors: **{report['engineErrors']}**",
        f"- Timeouts/caps: **{report['timeouts']}**",
        "",
        "| Variant | Status | Winner seat | Kinnan won | T4 assembly | Protected attempt | Prompts |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {variant} | {status} | {winnerSeat} | {kinnanWon} | {deterministicT4} | "
            "{protectedAttempt} | {prompts} |".format(**row)
        )
    (REPORT / "gate-report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["gatePassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
