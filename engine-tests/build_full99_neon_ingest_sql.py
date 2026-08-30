#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def q(v: Any) -> str:
    if v is None:
        return 'NULL'
    if isinstance(v, bool):
        return 'TRUE' if v else 'FALSE'
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def qjson(v: Any) -> str:
    return q(json.dumps(v, separators=(',', ':'), ensure_ascii=False)) + '::jsonb'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ndjson', required=True)
    ap.add_argument('--coverage', required=True)
    ap.add_argument('--run-key', required=True)
    ap.add_argument('--source-run-id', type=int)
    ap.add_argument('--artifact-name', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    coverage = json.loads(Path(args.coverage).read_text())
    rows = [json.loads(x) for x in Path(args.ndjson).read_text().splitlines() if x.strip()]
    assert coverage['telemetryComplete'] is True
    assert coverage['schemaVersion'] == 'kinnan-full99-card-telemetry-v2'
    assert coverage['actualRows'] == coverage['expectedRows'] == len(rows)
    assert coverage['duplicates'] == 0
    assert coverage['gamesWithExactly99'] == coverage['validGames']
    assert not coverage['missingCards']

    distinct = {}
    for r in rows:
        k = (r['canonicalKey'], r['cardIdentity'])
        if k in distinct:
            raise SystemExit(f'duplicate telemetry key: {k}')
        distinct[k] = r

    games = {r['canonicalKey'] for r in rows}
    for game in games:
        count = sum(1 for r in rows if r['canonicalKey'] == game)
        if count != 99:
            raise SystemExit(f'{game}: expected 99 cards, got {count}')

    sql = ['BEGIN;', 'CREATE SCHEMA IF NOT EXISTS cedh;', Path('database/cedh-full99-telemetry.sql').read_text()]
    sql.append(
        'INSERT INTO cedh.full99_telemetry_runs '
        '(run_key,source_run_id,artifact_name,schema_version,valid_games,expected_rows,actual_rows,games_with_exactly_99,missing_cards,duplicate_rows,telemetry_complete) VALUES ('
        + ','.join([
            q(args.run_key), q(args.source_run_id), q(args.artifact_name), q(coverage['schemaVersion']),
            q(coverage['validGames']), q(coverage['expectedRows']), q(coverage['actualRows']),
            q(coverage['gamesWithExactly99']), qjson(coverage['missingCards']), q(coverage['duplicates']), True and 'TRUE'
        ])
        + ') ON CONFLICT (run_key) DO UPDATE SET '
          'source_run_id=EXCLUDED.source_run_id,artifact_name=EXCLUDED.artifact_name,schema_version=EXCLUDED.schema_version,'
          'valid_games=EXCLUDED.valid_games,expected_rows=EXCLUDED.expected_rows,actual_rows=EXCLUDED.actual_rows,'
          'games_with_exactly_99=EXCLUDED.games_with_exactly_99,missing_cards=EXCLUDED.missing_cards,'
          'duplicate_rows=EXCLUDED.duplicate_rows,telemetry_complete=EXCLUDED.telemetry_complete;'
    )

    cols = '(run_key,schema_version,deck_hash,variant,canonical_key,seed,seat,pod,card_identity,present,opening_hand,kept,mulliganed,put_back,seen,first_seen_turn,drawn,first_drawn_turn,zones_by_turn,zone_changes,tutored,revealed,cast_or_played,cast_or_played_turns,mana_produced,mana_spent,mana_pool_before_actions,activated,used,combo_participation,protection_participation,interaction_participation,outcome_attribution,assembly_t4,attempt_t4,protected_attempt_t4,natural_win,package_execution,failure_code)'
    values = []
    for r in rows:
        values.append('(' + ','.join([
            q(args.run_key), q(r['schemaVersion']), q(r['deckHash']), q(r['variant']), q(r['canonicalKey']),
            q(r['seed']), q(r['seat']), q(r['pod']), q(r['cardIdentity']), q(r['present']), q(r['openingHand']),
            q(r['kept']), q(r['mulliganed']), q(r['putBack']), q(r['seen']), q(r['firstSeenTurn']), q(r['drawn']),
            q(r['firstDrawnTurn']), qjson(r['zonesByTurn']), qjson(r['zoneChanges']), q(r['tutored']), q(r['revealed']),
            q(r['castOrPlayed']), qjson(r['castOrPlayedTurns']), q(r['manaProduced']), q(r['manaSpent']),
            qjson(r['manaPoolBeforeActions']), q(r['activated']), q(r['used']), q(r['comboParticipation']),
            q(r['protectionParticipation']), q(r['interactionParticipation']), qjson(r['outcomeAttribution']),
            q(r['assemblyT4']), q(r['attemptT4']), q(r['protectedAttemptT4']), q(r['naturalWin']),
            q(r['packageExecution']), q(r['failureCode'])
        ]) + ')')

    sql.append('INSERT INTO cedh.full99_game_card_telemetry ' + cols + ' VALUES\n' + ',\n'.join(values) +
               '\nON CONFLICT (run_key,canonical_key,card_identity) DO UPDATE SET '
               'schema_version=EXCLUDED.schema_version,deck_hash=EXCLUDED.deck_hash,variant=EXCLUDED.variant,'
               'seed=EXCLUDED.seed,seat=EXCLUDED.seat,pod=EXCLUDED.pod,present=EXCLUDED.present,'
               'opening_hand=EXCLUDED.opening_hand,kept=EXCLUDED.kept,mulliganed=EXCLUDED.mulliganed,'
               'put_back=EXCLUDED.put_back,seen=EXCLUDED.seen,first_seen_turn=EXCLUDED.first_seen_turn,'
               'drawn=EXCLUDED.drawn,first_drawn_turn=EXCLUDED.first_drawn_turn,zones_by_turn=EXCLUDED.zones_by_turn,'
               'zone_changes=EXCLUDED.zone_changes,tutored=EXCLUDED.tutored,revealed=EXCLUDED.revealed,'
               'cast_or_played=EXCLUDED.cast_or_played,cast_or_played_turns=EXCLUDED.cast_or_played_turns,'
               'mana_produced=EXCLUDED.mana_produced,mana_spent=EXCLUDED.mana_spent,'
               'mana_pool_before_actions=EXCLUDED.mana_pool_before_actions,activated=EXCLUDED.activated,used=EXCLUDED.used,'
               'combo_participation=EXCLUDED.combo_participation,protection_participation=EXCLUDED.protection_participation,'
               'interaction_participation=EXCLUDED.interaction_participation,outcome_attribution=EXCLUDED.outcome_attribution,'
               'assembly_t4=EXCLUDED.assembly_t4,attempt_t4=EXCLUDED.attempt_t4,'
               'protected_attempt_t4=EXCLUDED.protected_attempt_t4,natural_win=EXCLUDED.natural_win,'
               'package_execution=EXCLUDED.package_execution,failure_code=EXCLUDED.failure_code;')

    sql.append('COMMIT;')
    Path(args.out).write_text('\n'.join(sql) + '\n')
    print(json.dumps({'runKey': args.run_key, 'validGames': coverage['validGames'], 'rows': len(rows), 'games': len(games), 'telemetryComplete': True}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
