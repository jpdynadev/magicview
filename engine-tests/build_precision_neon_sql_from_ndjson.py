#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import build_neon_ingest_sql as b

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--experiment-id',required=True); ap.add_argument('--batch-size',type=int,default=100); args=ap.parse_args()
    root=Path(args.root); src=root/'games.ndjson'; out=root/'sql'; out.mkdir(parents=True,exist_ok=True)
    games=[]
    with src.open() as f:
        for line in f:
            line=line.strip()
            if line: games.append(json.loads(line))
    if len(games)!=8800: raise SystemExit(f'expected 8800 records, got {len(games)}')
    byv={v:[] for v in b.PRECISION_MUTATIONS}
    for g in games:
        v=str(g.get('variant') or g.get('recoveredVariant') or '')
        if v not in byv: raise SystemExit(f'unknown variant {v!r}')
        byv[v].append(g)
    variant_sha={}
    for v,items in byv.items():
        for g in items:
            s=g.get('variantDeckSha256')
            if s: variant_sha[v]=str(s); break
        if v not in variant_sha:
            # Historical crash-only subsets may omit hash; derive stable variant identity without pretending it is a current deck hash.
            variant_sha[v]=hashlib.sha256(f'precision-31888564541:{v}'.encode()).hexdigest()
    vs=['BEGIN;']
    for v,(cuts,adds) in b.PRECISION_MUTATIONS.items():
        vs.append("INSERT INTO sim_variants (experiment_id,code,deck_name,deck_sha256,parent_code,mutation,exposure_cards) VALUES ("+','.join([b.q(args.experiment_id),b.q(v),b.q(v),b.q(variant_sha[v]),b.q(None if v=='P00_F10' else 'P00_F10'),b.qjson({'cuts':cuts,'adds':adds,'source':'precision-31888564541'}),b.qtext_array(adds)])+") ON CONFLICT (experiment_id,code) DO UPDATE SET deck_sha256=EXCLUDED.deck_sha256,mutation=EXCLUDED.mutation,exposure_cards=EXCLUDED.exposure_cards;")
    vs.append('COMMIT;'); (out/'000-variants.sql').write_text('\n'.join(vs)+'\n')
    records=[]
    for g in games:
        v=str(g.get('variant') or g.get('recoveredVariant'))
        mode=str(g.get('recoveredMode') or g.get('mode') or ('adversarial' if g.get('recoveredPod') else 'screen'))
        if mode not in ('screen','adversarial'): mode='adversarial' if mode in ('confirm','confirmation') else 'screen'
        pod=str(g.get('recoveredPod') or g.get('pod') or ('screen' if mode=='screen' else 'mixed'))
        r=b.normalized_record(g,corpus='precision',source='precision-31888564541',mode=mode,pod=pod,variant_sha=variant_sha[v])
        records.append((v,'screen' if mode=='screen' else 'confirm',r))
    manifest={'experimentId':args.experiment_id,'source':'precision-31888564541','corpus':'precision','records':len(records),'batchSize':args.batch_size,'sqlFiles':['000-variants.sql'],'sha256':{}}
    for no,start in enumerate(range(0,len(records),args.batch_size),1):
        batch=records[start:start+args.batch_size]
        gv=',\n'.join(b.game_values(r) for _,_,r in batch)
        lv=',\n'.join('('+','.join([b.q(args.experiment_id),f"(SELECT id FROM sim_variants WHERE experiment_id={b.q(args.experiment_id)} AND code={b.q(v)})",b.q(r['cache_key']),b.q(stage),f"(SELECT exposure_cards FROM sim_variants WHERE experiment_id={b.q(args.experiment_id)} AND code={b.q(v)})"])+')' for v,stage,r in batch)
        sql='BEGIN;\nINSERT INTO sim_game_results '+b.GAME_COLUMNS+' VALUES\n'+gv+'\nON CONFLICT (cache_key) DO NOTHING;\nINSERT INTO sim_experiment_games (experiment_id,variant_id,cache_key,stage,exposure_cards) VALUES\n'+lv+'\nON CONFLICT DO NOTHING;\nCOMMIT;\n'
        name=f'{no:03d}-games.sql'; (out/name).write_text(sql); manifest['sqlFiles'].append(name); manifest['sha256'][name]=hashlib.sha256(sql.encode()).hexdigest()
    manifest['sha256']['000-variants.sql']=hashlib.sha256((out/'000-variants.sql').read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'records':len(records),'files':len(manifest['sqlFiles'])},indent=2))
if __name__=='__main__': main()
