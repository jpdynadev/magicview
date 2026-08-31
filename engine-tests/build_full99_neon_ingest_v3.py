#!/usr/bin/env python3
"""Convert telemetry-complete v3 artifacts into idempotent Neon SQL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "kinnan-full99-card-telemetry-v3"


def q(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def qj(value: Any) -> str:
    return q(json.dumps(value, separators=(",", ":"))) + "::jsonb"


def validate_game(game: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    rows = list(game.get("cardTelemetryV3Rows") or [])
    coverage = game.get("cardTelemetryV3Coverage") or {}
    ids = [str(row.get("registeredCardId") or "") for row in rows]
    game_ids = {str(row.get("gameId") or "") for row in rows}
    if not game.get("telemetryV3Complete") or not coverage.get("valid"):
        raise ValueError("artifact is not telemetry-v3 complete")
    if len(rows) != 99 or len(set(ids)) != 99 or not all(ids):
        raise ValueError("v3 ingestion requires exactly 99 distinct registered-card rows")
    if len(game_ids) != 1 or not next(iter(game_ids)):
        raise ValueError("v3 ingestion requires one stable game identity")
    if any(row.get("schemaVersion") != SCHEMA for row in rows):
        raise ValueError("mixed or unsupported telemetry schema")
    return next(iter(game_ids)), rows


def build_sql(games: list[dict[str, Any]]) -> str:
    statements: list[str] = []
    for game in games:
        game_id, rows = validate_game(game)
        trace = list(game.get("rawActionTrace") or [])
        trace_values = [
            q(game_id), q(game.get("engineId")), q(rows[0].get("deckHash")),
            q(game.get("variant")), q(game.get("seed")), q(game.get("kinnanSeat")),
            q(game.get("podProfile")), q(game.get("horizon") or 4),
            q(game.get("pilotVersion")), q(SCHEMA), qj(trace),
            q(game.get("rawActionTraceHash")), q(game.get("rawActionTraceEventCount") or 0),
        ]
        statements.append(
            "INSERT INTO public.sim_game_action_traces_v3 "
            "(game_id,engine_id,deck_hash,variant,seed,seat,pod,horizon,pilot_version,schema_version,raw_action_trace,raw_action_trace_hash,raw_action_trace_event_count) VALUES ("
            + ",".join(trace_values)
            + ") ON CONFLICT (game_id) DO NOTHING;"
        )
        values = []
        for row in rows:
            values.append("(" + ",".join([
                q(game_id), q(row.get("registeredCardId")), q(row.get("cardName")), q(row.get("deckHash")), q(row.get("schemaVersion")),
                q(row.get("seen")), q(row.get("openingHand")), q(row.get("kept")), q(row.get("mulliganed")), q(row.get("firstSeenTurn")), q(row.get("firstDrawnTurn")),
                qj(row.get("zoneChanges") or []), q(row.get("tutored")), q(row.get("revealed")), q(row.get("cast")), q(row.get("played")),
                qj(row.get("manaProduced") or {}), q(row.get("manaSpent") or 0), q(row.get("activated")), q(row.get("used")),
                q(row.get("comboParticipation")), q(row.get("protectionParticipation")), q(row.get("interactionParticipation")),
                q(row.get("attemptPresent")), q(row.get("protectedAttemptPresent")), q(row.get("naturalWinPresence")), q(row.get("packageExecution")), q(row.get("outcomeRole")),
            ]) + ")")
        statements.append(
            "INSERT INTO public.sim_game_card_telemetry_v3 "
            "(game_id,registered_card_id,card_name,deck_hash,schema_version,seen,opening_hand,kept,mulliganed,first_seen_turn,first_drawn_turn,zone_changes,tutored,revealed,cast,played,mana_produced,mana_spent,activated,used,combo_participation,protection_participation,interaction_participation,attempt_present,protected_attempt_present,natural_win_presence,package_execution,outcome_role) VALUES\n"
            + ",\n".join(values)
            + "\nON CONFLICT (game_id,registered_card_id) DO NOTHING;"
        )
    return "BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    value = json.loads(args.artifact.read_text())
    games = value if isinstance(value, list) else [value]
    sql = build_sql(games)
    args.output.write_text(sql)
    print(json.dumps({"games": len(games), "rows": 99 * len(games), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

