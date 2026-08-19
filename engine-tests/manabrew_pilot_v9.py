#!/usr/bin/env python3
"""Kinnan pilot v9: explicit London mulligan count + larger engine polling budget."""
import json, sys
import manabrew_pilot as base
import manabrew_pilot_v3 as v3
import manabrew_pilot_v8 as v8

_prev_response = base.response_for
_kinnan_mulligans = 0


def response_for_v9(prompt, snap, deck, player):
    global _kinnan_mulligans
    inp=prompt.get('input',{}) or {}
    typ=inp.get('type')
    if deck=='Kinnan' and typ=='mulligan':
        hand=base.zone_cards(snap,player,'hand')
        keep=v8.keep_hand_v8(deck,hand,_kinnan_mulligans)
        if not keep:
            _kinnan_mulligans += 1
        return {'type':'mulligan','output':{'type':'mulliganDecision','keep':keep}}
    return _prev_response(prompt,snap,deck,player)

base.response_for=response_for_v9


def main():
    global _kinnan_mulligans
    if len(sys.argv)<3:
        print('usage: manabrew_pilot_v9.py HARNESS_JAR FORGE_HOME [seed ...]',file=sys.stderr)
        return 2
    jar,home=sys.argv[1],sys.argv[2]
    seeds=[int(x) for x in sys.argv[3:]] or [101,202]
    results=[]
    for seed in seeds:
        _kinnan_mulligans=0
        try:
            # The previous runner exhausted its outer polling loop on repeated
            # priority/stale-prompt polls even though only ~400 real decisions
            # occurred. A larger prompt budget raises that polling ceiling while
            # the round cap still bounds actual game length.
            r=v3.run_game(jar,home,seed,max_prompts=5000,max_round=5)
        except Exception as exc:
            r={'seed':seed,'status':'crash','error':repr(exc)}
        r['trackedKinnanMulligans']=_kinnan_mulligans
        print(json.dumps(r,sort_keys=True),flush=True)
        results.append(r)
    (base.RESULT_DIR/'pilot-summary.json').write_text(json.dumps(results,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
