#!/usr/bin/env python3
"""Build idempotent Neon SQL batches from recovered simulation corpora.

GitHub Actions never receives database credentials. It only normalizes immutable
records into SQL files; the connected Neon control-plane executes those files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

MANABREW_REF = '8a1380e5a59986ea3fed143b85f710f9ee3888dc'
COMPLETED = {'game_over', 'horizon_complete'}

PRECISION_MUTATIONS = {
    'P00_F10': ([], []),
    'P01_MISCAST': (['Dispel'], ['Miscast']),
    'P02_GSZ': (['Mystical Tutor'], ["Green Sun's Zenith"]),
    'P03_ELDRITCH': (['Mystical Tutor'], ['Eldritch Evolution']),
    'P04_TRIBUTE': (['Mystical Tutor'], ['Tribute Mage']),
    'P05_SEEDBORN': (["Nature's Rhythm"], ['Seedborn Muse']),
    'P06_HULLBREAKER': (['Mockingbird'], ['Hullbreaker Horror']),
    'P07_M30_MICRO': (['Dispel', 'Mockingbird'], ['Miscast', 'Consecrated Sphinx']),
}

ARCH_MUTATIONS = {
    'F10': ([], []),
    'COPY_CORE': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum'], ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Mirage Mirror']),
    'COPY_CREATURE': (["Nature's Rhythm", 'Energy Refractor', 'Dispel'], ['Flesh Duplicate', 'Clever Impersonator', 'Gene Pollinator']),
    'DRUID_EFFIGY': (["Nature's Rhythm", 'Energy Refractor', 'Dispel'], ['Devoted Druid', "Machine God's Effigy", 'Gene Pollinator']),
    'COPY_DRUID': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection'], ['Devoted Druid', "Machine God's Effigy", 'Flesh Duplicate', 'Copy Enchantment', 'Gene Pollinator']),
    'COPY_HEAVY': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection', 'Hydroelectric Specimen'], ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Mirage Mirror', 'Clever Impersonator', 'Gene Pollinator']),
    'COPY_ARTIFACT': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Hydroelectric Specimen'], ['Copy Artifact', 'Mirage Mirror', 'Phyrexian Metamorph', 'Flesh Duplicate']),
    'COPY_PROTECTED': (["Nature's Rhythm", 'Energy Refractor', 'Springleaf Drum', 'Hydroelectric Specimen'], ['Copy Enchantment', 'Copy Artifact', 'Flesh Duplicate', 'Gene Pollinator']),
    'DRUID_TUTOR': (['Energy Refractor', 'Dispel', 'Springleaf Drum', 'Hydroelectric Specimen'], ['Devoted Druid', "Machine God's Effigy", "Green Sun's Zenith", 'Eldritch Evolution']),
    'TUTOR_DENSE': (['Energy Refractor', 'Dispel', 'Springleaf Drum', 'Hydroelectric Specimen'], ["Green Sun's Zenith", 'Eldritch Evolution', 'Tribute Mage', 'Devoted Druid']),
    'NODE_DENSE': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Springleaf Drum', 'Misdirection', 'Hydroelectric Specimen'], ['Devoted Druid', "Machine God's Effigy", 'Copy Artifact', 'Flesh Duplicate', "Green Sun's Zenith", 'Eldritch Evolution']),
    'COPY_VALUE': (["Nature's Rhythm", 'Energy Refractor', 'Dispel', 'Hydroelectric Specimen'], ['Copy Enchantment', 'Flesh Duplicate', 'Clever Impersonator', 'Gene Pollinator']),
}


def q(value: Any) -> str:
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def qjson(value: Any) -> str:
    return q(json.dumps(value, separators=(',', ':'), ensure_ascii=False)) + '::jsonb'


def qtext_array(values: list[str]) -> str:
    if not values:
        return "'{}'::text[]"
    return 'ARRAY[' + ','.join(q(v) for v in values) + ']::text[]'


def pod_hash(hashes: list[str], fallback: str) -> str:
    if hashes:
        return hashlib.sha256(json.dumps(hashes, separators=(',', ':')).encode()).hexdigest()
    return hashlib.sha256(fallback.encode()).hexdigest()


def legacy_hands(g: dict[str, Any]) -> tuple[list[str], list[str], list[str], int | None]:
    seat = str(g.get('kinnanSeat'))
    opening = list((g.get('openingHands') or {}).get(seat, []) or [])
    kept = list((g.get('keptHands') or {}).get(seat, []) or [])
    protection = list(g.get('protectionAvailable') or [])
    observed = sorted(set(opening) | set(kept) | set(protection))
    mull = (g.get('mulligans') or {}).get(seat)
    return opening, kept, observed, mull


def normalized_record(g: dict[str, Any], *, corpus: str, source: str, mode: str, pod: str, variant_sha: str) -> dict[str, Any]:
    seat = int(g.get('kinnanSeat', 0))
    seed = int(g.get('seed', 0))
    if corpus == 'precision':
        opening, kept, observed, mull = legacy_hands(g)
        certified = bool(g.get('certifiedDeterministicAttempt'))
        t = g.get('firstAttemptTurn')
        strict = bool(g.get('protectedAttempt')) and certified and t is not None and int(t) <= 4
        exposure_quality = 'opening_kept_protection_only'
        optimizer = 'historical-precision'
        profile = 'legacy-precision-v1'
        engine = f'{MANABREW_REF}:historical-precision'
        max_round = 4 if mode == 'screen' else 5
        observed_events: list[dict[str, Any]] = []
    else:
        opening = list(g.get('openingHand') or [])
        kept = list(g.get('keptHand') or [])
        observed = list(g.get('observedCards') or [])
        mull = g.get('mulligans')
        certified = bool(g.get('certifiedDeterministicAttempt'))
        strict = bool(g.get('strictProtectedT4'))
        exposure_quality = 'live_zones_and_small_choice_pools'
        optimizer = str(g.get('optimizerId') or 'unknown')
        profile = str(g.get('executionProfile') or 'unknown')
        engine = f'{MANABREW_REF}:arch-cold-v1' + (f':{pod}' if mode == 'adversarial' else '')
        max_round = 4 if mode == 'screen' else 5
        observed_events = list(g.get('observedCardEvents') or g.get('exposureEvents') or [])
    hashes = list(g.get('seatDeckSha256s') or [])
    deck_sha = str(g.get('variantDeckSha256') or variant_sha)
    cache_payload = {'corpus': corpus, 'source': source, 'variant': g.get('variant'), 'mode': mode, 'pod': pod, 'seed': seed, 'seat': seat, 'deck': deck_sha}
    cache_key = hashlib.sha256(json.dumps(cache_payload, sort_keys=True).encode()).hexdigest()
    return {
        'cache_key': cache_key,
        'engine_id': engine,
        'pilot_version': str(g.get('pilotVersion') or 'unknown'),
        'optimizer_id': optimizer,
        'execution_profile': profile,
        'deck_sha256': deck_sha,
        'pod_deck_sha256': str(g.get('podDeckSha256') or pod_hash(hashes, f'{source}:{seed}:{seat}:{pod}')),
        'seat_deck_sha256s': hashes,
        'mode': mode,
        'pod': pod,
        'seed': seed,
        'seat': seat,
        'max_round': max_round,
        'status': str(g.get('status') or 'unknown'),
        'winner_seat': g.get('winnerSeat'),
        'kinnan_won': bool(g.get('kinnanWon')),
        'first_assembly_turn': g.get('firstAssemblyTurn'),
        'first_attempt_turn': g.get('firstAttemptTurn'),
        'deterministic_t4': bool(g.get('deterministicT4')),
        'certified_attempt': certified,
        'protected_attempt': bool(g.get('protectedAttempt')),
        'strict_protected_t4': strict,
        'combo_line': g.get('comboLine'),
        'failure_code': g.get('primaryFailureCode'),
        'wall_ms': g.get('wallMs'),
        'prompts': g.get('prompts'),
        'mulligans': mull,
        'opening_hand': opening,
        'kept_hand': kept,
        'observed_cards': observed,
        'observed_card_events': observed_events,
        'v2_positive_early_exit': bool(g.get('v2EarlyExit')),
        'v2_deadline_early_exit': bool(g.get('v2DeadlineExit')),
        'audit': {
            'source': source,
            'corpus': corpus,
            'historical': corpus == 'precision',
            'exposure_quality': exposure_quality,
            'raw_error': g.get('error'),
            'naturalWinAfterAttempt': g.get('naturalWinAfterAttempt'),
            'attemptResolved': g.get('attemptResolved'),
        },
    }


def game_values(r: dict[str, Any]) -> str:
    return '(' + ','.join([
        q(r['cache_key']), q(r['engine_id']), q(r['pilot_version']), q(r['optimizer_id']), q(r['execution_profile']),
        q(r['deck_sha256']), q(r['pod_deck_sha256']), qtext_array(r['seat_deck_sha256s']), q(r['mode']), q(r['pod']),
        q(r['seed']), q(r['seat']), q(r['max_round']), q(r['status']), q(r['winner_seat']), q(r['kinnan_won']),
        q(r['first_assembly_turn']), q(r['first_attempt_turn']), q(r['deterministic_t4']), q(r['certified_attempt']),
        q(r['protected_attempt']), q(r['strict_protected_t4']), q(r['combo_line']), q(r['failure_code']), q(r['wall_ms']),
        q(r['prompts']), q(r['mulligans']), qjson(r['opening_hand']), qjson(r['kept_hand']), qtext_array(r['observed_cards']),
        qjson(r['observed_card_events']), q(r['v2_positive_early_exit']), q(r['v2_deadline_early_exit']), qjson(r['audit'])
    ]) + ')'


GAME_COLUMNS = '(cache_key,engine_id,pilot_version,optimizer_id,execution_profile,deck_sha256,pod_deck_sha256,seat_deck_sha256s,mode,pod,seed,seat,max_round,status,winner_seat,kinnan_won,first_assembly_turn,first_attempt_turn,deterministic_t4,certified_attempt,protected_attempt,strict_protected_t4,combo_line,failure_code,wall_ms,prompts,mulligans,opening_hand,kept_hand,observed_cards,observed_card_events,v2_positive_early_exit,v2_deadline_early_exit,audit)'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', choices=['precision', 'bridge'], required=True)
    ap.add_argument('--root', required=True)
    ap.add_argument('--experiment-id', required=True)
    ap.add_argument('--source', required=True)
    ap.add_argument('--batch-size', type=int, default=100)
    args = ap.parse_args()
    root = Path(args.root)
    mutations = PRECISION_MUTATIONS if args.corpus == 'precision' else ARCH_MUTATIONS
    files: list[tuple[str, str, str, Path]] = []
    if args.corpus == 'precision':
        for v in mutations:
            files.append((v, 'screen', 'screen', root / f'screen-{v}.json'))
        for v in ('P00_F10', 'P02_GSZ', 'P03_ELDRITCH'):
            files.append((v, 'adversarial', '*', root / f'adv-{v}.json'))
    else:
        for v in mutations:
            files.append((v, 'screen', 'screen', root / f'{v}.json'))

    parsed: dict[str, list[dict[str, Any]]] = {}
    variant_sha: dict[str, str] = {}
    for v, mode, _, path in files:
        if not path.exists():
            raise SystemExit(f'missing corpus file {path}')
        games = json.loads(path.read_text())
        parsed[str(path)] = games
        for g in games:
            if g.get('variantDeckSha256'):
                variant_sha[v] = str(g['variantDeckSha256'])
                break
    missing_sha = [v for v in mutations if v not in variant_sha]
    if missing_sha:
        raise SystemExit(f'no deck hash for variants {missing_sha}')

    sql_dir = root / 'sql'
    sql_dir.mkdir(parents=True, exist_ok=True)
    variant_sql = ['BEGIN;']
    for v, (cuts, adds) in mutations.items():
        variant_sql.append(
            "INSERT INTO sim_variants (experiment_id,code,deck_name,deck_sha256,parent_code,mutation,exposure_cards) VALUES ("
            + ','.join([
                q(args.experiment_id), q(v), q(v), q(variant_sha[v]), q(None if v in {'P00_F10','F10'} else ('P00_F10' if args.corpus=='precision' else 'F10')),
                qjson({'cuts': cuts, 'adds': adds, 'source': args.source}), qtext_array(adds)
            ])
            + ") ON CONFLICT (experiment_id,code) DO UPDATE SET deck_sha256=EXCLUDED.deck_sha256,mutation=EXCLUDED.mutation,exposure_cards=EXCLUDED.exposure_cards;"
        )
    variant_sql.append('COMMIT;')
    (sql_dir / '000-variants.sql').write_text('\n'.join(variant_sql) + '\n')

    records: list[tuple[str, str, dict[str, Any]]] = []
    for v, mode, pod_marker, path in files:
        for g in parsed[str(path)]:
            pod = str(g.get('recoveredPod') or g.get('pod') or ('screen' if mode == 'screen' else pod_marker))
            records.append((v, 'screen' if mode == 'screen' else 'confirm', normalized_record(g, corpus=args.corpus, source=args.source, mode=mode, pod=pod, variant_sha=variant_sha[v])))

    manifest = {'experimentId': args.experiment_id, 'source': args.source, 'corpus': args.corpus, 'records': len(records), 'batchSize': args.batch_size, 'sqlFiles': ['000-variants.sql']}
    for batch_no, start in enumerate(range(0, len(records), args.batch_size), start=1):
        batch = records[start:start+args.batch_size]
        game_values_sql = ',\n'.join(game_values(r) for _, _, r in batch)
        link_values = ',\n'.join(
            '(' + ','.join([
                q(args.experiment_id),
                f"(SELECT id FROM sim_variants WHERE experiment_id={q(args.experiment_id)} AND code={q(v)})",
                q(r['cache_key']), q(stage),
                f"(SELECT exposure_cards FROM sim_variants WHERE experiment_id={q(args.experiment_id)} AND code={q(v)})"
            ]) + ')'
            for v, stage, r in batch
        )
        sql = (
            'BEGIN;\nINSERT INTO sim_game_results ' + GAME_COLUMNS + ' VALUES\n' + game_values_sql + '\nON CONFLICT (cache_key) DO NOTHING;\n'
            + 'INSERT INTO sim_experiment_games (experiment_id,variant_id,cache_key,stage,exposure_cards) VALUES\n' + link_values + '\nON CONFLICT DO NOTHING;\nCOMMIT;\n'
        )
        name = f'{batch_no:03d}-games.sql'
        (sql_dir / name).write_text(sql)
        manifest['sqlFiles'].append(name)
    (sql_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
