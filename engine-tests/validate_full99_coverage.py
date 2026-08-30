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
    semantic_failures = []
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
        trace = game.get("rawActionTrace") or []
        has_look_prompt = any(
            e.get("kind") == "promptDecision" and e.get("promptType") == "revealCards"
            and ((e.get("inputSummary") or {}).get("cards") or [])
            for e in trace
        )
        source_text = {}
        for event in trace:
            if event.get("kind") != "actionChosen":
                continue
            raw_card = event.get("rawCard") or {}
            name = str(((raw_card.get("identity") or {}).get("name") or event.get("card") or ""))
            if name:
                source_text[name] = str(raw_card.get("text") or "")
        has_search_choice = any(
            e.get("kind") == "promptDecision" and e.get("promptType") == "chooseCards"
            and ((e.get("chosenOutput") or {}).get("chosenCardIds") or [])
            and "search your library" in source_text.get(
                str((((e.get("inputSummary") or {}).get("presentation") or {}).get("title") or "")), ""
            ).lower()
            for e in trace
        )
        has_search_reveal_choice = any(
            e.get("kind") == "promptDecision" and e.get("promptType") == "chooseCards"
            and ((e.get("chosenOutput") or {}).get("chosenCardIds") or [])
            and "reveal" in source_text.get(
                str((((e.get("inputSummary") or {}).get("presentation") or {}).get("title") or "")), ""
            ).lower()
            for e in trace
        )
        paid_casts = [
            e for e in trace
            if e.get("kind") == "actionChosen" and e.get("actionType") == "cast"
            and not str(e.get("description") or "").lower().startswith("play ")
            and int(((e.get("rawCard") or {}).get("cmc") or 0)) > 0
        ]
        reasons = []
        if has_look_prompt and not any(r.get("lookedAt") for r in rows):
            reasons.append("card-look prompts were observed but no per-card looked-at attribution was persisted")
        if has_search_choice and not any(r.get("tutored") for r in rows):
            reasons.append("search choices were observed but no per-card tutor attribution was persisted")
        if has_search_reveal_choice and not any(r.get("revealed") for r in rows):
            reasons.append("a reveal-search choice was observed but no per-card reveal attribution was persisted")
        if paid_casts and not all(r.get("manaAttributionComplete") for r in rows if r.get("cast")):
            reasons.append("one or more paid casts lacks exact mana produced/spent attribution")
        if reasons:
            semantic_failures.append({
                "key": [game.get("variant"), game.get("seed"), game.get("kinnanSeat"), game.get("podProfile")],
                "reasons": reasons,
            })
    report = {
        "schemaVersion": SCHEMA,
        "validGames": len(valid),
        "expectedRows": len(valid) * 99,
        "actualRows": sum(len(g.get("cardTelemetryRows") or []) for g in valid),
        "missingCards": sum(max(0, 99 - len(set(r.get("card") for r in (g.get("cardTelemetryRows") or [])))) for g in valid),
        "duplicateGames": failures,
        "semanticFailures": semantic_failures,
        "coverageValid": bool(valid) and not failures,
        "semanticValid": bool(valid) and not semantic_failures,
        "telemetryComplete": bool(valid) and not failures and not semantic_failures,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["telemetryComplete"] or report["actualRows"] != report["expectedRows"]:
        raise SystemExit("full-99 telemetry coverage failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
