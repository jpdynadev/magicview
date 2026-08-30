#!/usr/bin/env python3
"""Convert validated full-99 game artifacts into idempotent Neon SQL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def q(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def qj(value):
    return q(json.dumps(value, separators=(",", ":"))) + "::jsonb"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    value = json.loads(Path(args.artifact).read_text())
    games = value if isinstance(value, list) else [value]
    rows = []
    for game in games:
        telemetry = game.get("cardTelemetryRows") or []
        if len(telemetry) != 99 or len({r.get("card") for r in telemetry}) != 99:
            raise SystemExit(f"coverage failure for {game.get('variant')} seed={game.get('seed')}")
        trace = game.get("rawActionTrace") or []
        for row in telemetry:
            rows.append("(" + ",".join([
                q(game.get("engineId")), q(row.get("deckHash")), q(row.get("variant")),
                q(row.get("seed")), q(row.get("seat")), q(row.get("pod")), q(row.get("card")),
                q(row.get("schemaVersion")), q(row.get("openingHand")), q(row.get("kept")),
                q(row.get("mulliganed")), q(row.get("firstSeenTurn")), q(row.get("firstDrawnTurn")),
                qj(row.get("zonesSeen") or []), qj(row.get("zoneChanges") or []),
                q(row.get("tutored")), q(row.get("revealed")), q(row.get("cast")), q(row.get("played")),
                q(row.get("manaProduced") or 0), q(row.get("manaSpent") or 0), q(row.get("activated")),
                q(row.get("used")), q(row.get("comboParticipation")), q(row.get("protectionParticipation")),
                q(row.get("interactionParticipation")), q(row.get("naturalWinPresence")),
                q(row.get("assemblyPresence")), q(row.get("attemptPresence")),
                q(row.get("protectedAttemptPresence")), q(row.get("packageExecution")),
                q(row.get("outcomeAttribution")), qj(trace),
            ]) + ")")
    columns = "(engine_id,deck_hash,variant,seed,seat,pod,card_identity,schema_version,opening_hand,kept,mulliganed,first_seen_turn,first_drawn_turn,zones_seen,zone_changes,tutored,revealed,cast,played,mana_produced,mana_spent,activated,used,combo_participation,protection_participation,interaction_participation,natural_win_presence,assembly_presence,attempt_presence,protected_attempt_presence,package_execution,outcome_attribution,raw_action_trace)"
    sql = "INSERT INTO public.sim_game_card_telemetry " + columns + " VALUES\n" + ",\n".join(rows) + "\nON CONFLICT DO NOTHING;\n"
    Path(args.output).write_text(sql)
    print(json.dumps({"games": len(games), "rows": len(rows), "output": args.output}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
