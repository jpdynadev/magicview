#!/usr/bin/env python3
import json, subprocess, sys, time
import manabrew_pilot as base

RESULT_DIR = base.RESULT_DIR
DECKS = base.DECKS


def round_from_global_turn(turn):
    try:
        t=int(turn or 0)
    except Exception:
        return 0
    return 0 if t <= 0 else ((t - 1) // 4) + 1


def payment_action_kind(action):
    return action.get('type','')


def choose_productive_payment(inp):
    # Confirm immediately once the pool can satisfy the remaining cost.
    if inp.get('canConfirmFromPool'):
        return {'type':'payManaCost','output':{'type':'pay','auto':True}}, False

    actions=inp.get('actions',[]) or []
    productive=[]
    for a in actions:
        kind=payment_action_kind(a)
        # Never choose undo/release actions while trying to complete a payment.
        if kind in {'undoMana','releaseResource'}:
            continue
        if kind in {'activateManaAbility','useResource','payLife'}:
            productive.append(a)

    if productive:
        def score(a):
            s=json.dumps(a)
            # Prefer actual mana activations; colored sources over colorless when tied.
            v=20 if a.get('type')=='activateManaAbility' else 10
            if any(f'"{c}"' in s for c in ['U','G','B','R','W']): v += 5
            if '"C"' in s: v += 1
            return v
        chosen=max(productive,key=score)
        return {'type':'payManaCost','output':{'type':'act','actionId':chosen['id']}}, False

    # The spell cannot currently be fully paid. Cancel rather than undo/retap forever.
    return {'type':'payManaCost','output':{'type':'cancel'}}, True


def summarize_prompt(inp):
    typ=inp.get('type')
    if typ=='chooseAction':
        return {'type':typ,'actions':[{k:a.get(k) for k in ('id','type','cardId','label','description','isManaAbility','cost','producedMana') if k in a} for a in inp.get('actions',[])]}
    if typ=='payManaCost':
        return {'type':typ,'cardId':inp.get('cardId'),'cardName':inp.get('cardName'),'manaCost':inp.get('manaCost'),
                'canConfirmFromPool':inp.get('canConfirmFromPool'),
                'actions':[{k:a.get(k) for k in ('id','type','cardId','description','isManaAbility','cost','producedMana','resource','amount') if k in a} for a in inp.get('actions',[])]}
    if typ=='chooseCards':
        return {'type':typ,'min':inp.get('min'),'max':inp.get('max'),'cards':[{'id':c.get('id'),'name':base.card_name(c)} for c in inp.get('cards',[])]}
    if typ=='chooseBoardTargets':
        return {'type':typ,'cancellable':inp.get('cancellable'),'candidates':inp.get('candidates',[]),'presentation':inp.get('presentation')}
    return {'type':typ,'presentation':inp.get('presentation')}


def deterministic_kinnan_state(snap):
    bf=base.zone_cards(snap,0,'battlefield')
    names={base.card_name(c) for c in bf}
    hand={base.card_name(c) for c in base.zone_cards(snap,0,'hand')}
    if {'Kinnan, Bonder Prodigy','Basalt Monolith'} <= names:
        outlet = bool((names|hand) & {'Staff of Domination','Thrasios, Triton Hero','Stonework Packbeast','Energy Refractor','Agatha\'s Soul Cauldron','Walking Ballista'})
        if outlet:
            return 'Kinnan + Basalt + deterministic outlet/access'
    # Effigy copies the creature characteristics while remaining an artifact/noncreature.
    # Treat any battlefield Devoted Druid object whose serialized card data says artifact
    # but not creature as the Effigy copy. Keep broad fallbacks for protocol shape changes.
    for c in bf:
        if base.card_name(c)!='Devoted Druid':
            continue
        raw=json.dumps(c).lower()
        if 'artifact' in raw and ('creature' not in raw or "machine god's effigy" in raw):
            if 'Kinnan, Bonder Prodigy' in names or bool((names|hand) & {'Staff of Domination','Thrasios, Triton Hero','Walking Ballista'}):
                return "Machine God's Effigy(copy Devoted Druid) infinite mana + deterministic access"
    return None


def run_game(jar, forge_home, seed, max_prompts=2500, max_round=5):
    trace=[]; errors=[]; failed_cast_states=set()
    proc=subprocess.Popen(
        ['java','-Xmx4g','-jar',jar,'--interactive-server','--forge-home',forge_home],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        payload={'gameId':f'cedh-v3-{seed}','variant':'Commander','startingLife':40,'seed':seed,'players':base.build_players()}
        start=json.loads(base.rpc(proc,{'command':'startGame','payload':json.dumps(payload,separators=(',',':'))}))
        sid=start['sessionId']; last_prompt_id=None; idle=0
        result={'seed':seed,'status':'prompt_limit','winner':None,'deterministicKinnan':None,
                'globalTurn':None,'round':0,'prompts':0}

        for step in range(max_prompts*4):
            raw=base.rpc(proc,{'command':'getPrompt','sessionId':sid,'playerIndex':0})
            if not raw:
                idle+=1
                if idle>1500:
                    result['status']='idle_timeout'; break
                time.sleep(0.005); continue
            prompt=json.loads(raw); pid=prompt.get('promptId')
            if pid==last_prompt_id:
                idle+=1
                if idle>1500:
                    result['status']='stale_prompt_timeout'; break
                time.sleep(0.003); continue
            idle=0; last_prompt_id=pid

            deciding=prompt.get('decidingPlayerId') or 'player-0'
            try: p=int(str(deciding).split('-')[-1])
            except Exception: p=0
            if p<0 or p>=len(DECKS): p=0
            deck=DECKS[p][0]
            snap=json.loads(base.rpc(proc,{'command':'getSnapshot','sessionId':sid,'viewer':p}))
            gturn=snap.get('turn'); rnd=round_from_global_turn(gturn)
            result['globalTurn']=gturn; result['round']=rnd
            if rnd>max_round:
                result['status']='round_cap'; break

            kline=deterministic_kinnan_state(snap)
            if kline and not result['deterministicKinnan']:
                result['deterministicKinnan']={'globalTurn':gturn,'round':rnd,'line':kline,'promptId':pid}

            inp=prompt.get('input') or {}; typ=inp.get('type')
            bf_sig=tuple(sorted(base.battlefield_names(snap,p)))
            ans=None; canceled_unpayable=False

            try:
                if typ=='payManaCost':
                    ans,canceled_unpayable=choose_productive_payment(inp)
                    if canceled_unpayable and inp.get('cardId'):
                        failed_cast_states.add((gturn,snap.get('step'),p,inp.get('cardId'),bf_sig))
                elif typ=='chooseAction':
                    # Filter only casts that already failed payment in this exact board/phase state.
                    actions=inp.get('actions',[]) or []
                    filtered=[]
                    for a in actions:
                        key=(gturn,snap.get('step'),p,a.get('cardId'),bf_sig)
                        if a.get('type')=='cast' and key in failed_cast_states:
                            continue
                        filtered.append(a)
                    patched=dict(inp); patched['actions']=filtered
                    patched_prompt=dict(prompt); patched_prompt['input']=patched
                    ans=base.response_for(patched_prompt,snap,deck,p)
                else:
                    ans=base.response_for(prompt,snap,deck,p)
            except Exception as e:
                errors.append({'player':p,'deck':deck,'prompt':prompt,'error':repr(e)})
                result['status']='unsupported_prompt'; result['error']=repr(e)
                break

            trace.append({
                'promptId':pid,'player':p,'deck':deck,'decidingPlayerId':deciding,
                'globalTurn':gturn,'round':rnd,'stepName':snap.get('step'),
                'activePlayerId':snap.get('activePlayerId'),'priorityPlayerId':snap.get('priorityPlayerId'),
                'hand':[base.card_name(c) for c in base.zone_cards(snap,p,'hand')],
                'battlefield':[base.card_name(c) for c in base.zone_cards(snap,p,'battlefield')],
                'prompt':summarize_prompt(inp),'answer':ans,'canceledUnpayable':canceled_unpayable,
            })
            result['prompts']+=1
            if result['prompts']>=max_prompts:
                result['status']='prompt_cap'; break

            if typ=='gameOver':
                result['status']='game_over'; result['gameOverPrompt']=inp; break
            if ans is not None:
                base.rpc(proc,{'command':'submitAction','sessionId':sid,'payload':json.dumps(ans,separators=(',',':'))})

        if errors:
            (RESULT_DIR/f'pilot-errors-{seed}.json').write_text(json.dumps(errors,indent=2))
        (RESULT_DIR/f'pilot-trace-{seed}.json').write_text(json.dumps(trace,indent=2))
        return result
    finally:
        try: proc.terminate(); proc.wait(timeout=3)
        except Exception: proc.kill()
        err=proc.stderr.read() if proc.stderr else ''
        if err: (RESULT_DIR/f'pilot-stderr-{seed}.log').write_text(err)


def main():
    if len(sys.argv)<3:
        print('usage: manabrew_pilot_v3.py HARNESS_JAR FORGE_HOME [seed ...]',file=sys.stderr); return 2
    jar,home=sys.argv[1],sys.argv[2]
    seeds=[int(x) for x in sys.argv[3:]] or [101,202,303]
    results=[]
    for seed in seeds:
        try: r=run_game(jar,home,seed)
        except Exception as e: r={'seed':seed,'status':'crash','error':repr(e)}
        print(json.dumps(r,sort_keys=True),flush=True); results.append(r)
    (RESULT_DIR/'pilot-summary.json').write_text(json.dumps(results,indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
