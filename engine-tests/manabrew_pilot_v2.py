#!/usr/bin/env python3
import json, subprocess, sys, time
from pathlib import Path
import manabrew_pilot as base

RESULT_DIR = base.RESULT_DIR
DECKS = base.DECKS


def run_game(jar, forge_home, seed, max_prompts=5000):
    trace=[]; errors=[]
    proc=subprocess.Popen(
        ['java','-Xmx4g','-jar',jar,'--interactive-server','--forge-home',forge_home],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        payload={'gameId':f'cedh-{seed}','variant':'Commander','startingLife':40,'seed':seed,'players':base.build_players()}
        start=json.loads(base.rpc(proc,{'command':'startGame','payload':json.dumps(payload,separators=(',',':'))}))
        sid=start['sessionId']
        last_prompt_id=None
        result={'seed':seed,'status':'prompt_limit','winner':None,'deterministicKinnan':None,'turn':None,'prompts':0}
        idle=0

        for step in range(max_prompts):
            # The Manabrew harness exposes one global current prompt. playerIndex is a
            # viewer argument, not a per-seat queue. Route the prompt exactly once via
            # decidingPlayerId; otherwise duplicate answers remain in the shared queue.
            raw=base.rpc(proc,{'command':'getPrompt','sessionId':sid,'playerIndex':0})
            if not raw:
                idle += 1
                if idle > 3000:
                    result['status']='idle_timeout'
                    break
                time.sleep(0.01)
                continue

            prompt=json.loads(raw)
            pid=prompt.get('promptId')
            if pid == last_prompt_id:
                idle += 1
                if idle > 3000:
                    result['status']='stale_prompt_timeout'
                    break
                time.sleep(0.005)
                continue

            idle=0
            last_prompt_id=pid
            deciding=prompt.get('decidingPlayerId') or 'player-0'
            try:
                p=int(str(deciding).split('-')[-1])
            except Exception:
                p=0
            if p < 0 or p >= len(DECKS):
                p=0
            deck=DECKS[p][0]

            snap=json.loads(base.rpc(proc,{'command':'getSnapshot','sessionId':sid,'viewer':p}))
            result['turn']=snap.get('turn')
            kline=base.deterministic_kinnan_state(snap)
            if kline and not result['deterministicKinnan']:
                result['deterministicKinnan']={'turn':snap.get('turn'),'line':kline,'promptId':pid}

            typ=(prompt.get('input') or {}).get('type')
            trace.append({
                'step':step,'player':p,'deck':deck,'decidingPlayerId':deciding,
                'promptId':pid,'type':typ,'turn':snap.get('turn'),'stepName':snap.get('step'),
                'hand':[base.card_name(c) for c in base.zone_cards(snap,p,'hand')],
                'battlefield':[base.card_name(c) for c in base.zone_cards(snap,p,'battlefield')],
            })
            result['prompts'] += 1

            if typ=='gameOver':
                result['status']='game_over'
                result['gameOverPrompt']=prompt.get('input')
                # Preserve full game-over payload; winner decoding can be refined after first real sample.
                (RESULT_DIR/f'pilot-trace-{seed}.json').write_text(json.dumps(trace,indent=2))
                return result

            try:
                ans=base.response_for(prompt,snap,deck,p)
            except Exception as e:
                errors.append({'player':p,'deck':deck,'prompt':prompt,'error':repr(e)})
                result['status']='unsupported_prompt'; result['error']=repr(e)
                (RESULT_DIR/f'pilot-errors-{seed}.json').write_text(json.dumps(errors,indent=2))
                (RESULT_DIR/f'pilot-trace-{seed}.json').write_text(json.dumps(trace,indent=2))
                return result

            if ans is not None:
                base.rpc(proc,{
                    'command':'submitAction','sessionId':sid,
                    'payload':json.dumps(ans,separators=(',',':'))
                })

        (RESULT_DIR/f'pilot-trace-{seed}.json').write_text(json.dumps(trace,indent=2))
        return result
    finally:
        try:
            proc.terminate(); proc.wait(timeout=3)
        except Exception:
            proc.kill()
        err=proc.stderr.read() if proc.stderr else ''
        if err:
            (RESULT_DIR/f'pilot-stderr-{seed}.log').write_text(err)


def main():
    if len(sys.argv)<3:
        print('usage: manabrew_pilot_v2.py HARNESS_JAR FORGE_HOME [seed ...]',file=sys.stderr)
        return 2
    jar,home=sys.argv[1],sys.argv[2]
    seeds=[int(x) for x in sys.argv[3:]] or [101,202,303]
    results=[]
    for seed in seeds:
        try:
            r=run_game(jar,home,seed)
        except Exception as e:
            r={'seed':seed,'status':'crash','error':repr(e)}
        print(json.dumps(r,sort_keys=True),flush=True)
        results.append(r)
    (RESULT_DIR/'pilot-summary.json').write_text(json.dumps(results,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
