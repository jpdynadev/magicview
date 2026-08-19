#!/usr/bin/env python3
"""Kinnan pilot v8: fix deep-mulligan mana preservation and infinite-loop convergence."""
import json, sys
import manabrew_pilot as base
import manabrew_pilot_v3 as v3
import manabrew_pilot_v7 as v7
import manabrew_pilot_v5 as v5

_previous_response = base.response_for
_previous_target_score = base.kinnan_target_score

FLEX_BLUE = {'Hydroelectric Specimen', 'Sink into Stupor'}
ONE_G_DORKS = {'Birds of Paradise','Delighted Halfling','Elvish Mystic','Fyndhorn Elves','Llanowar Elves'}
DIRECT_ACCESS = {'Staff of Domination','Walking Ballista','Thrasios, Triton Hero'}


def _names(hand):
    return [base.card_name(c) for c in hand]


def _mana_profile(names):
    lands=[n for n in names if n in base.LANDS or n in FLEX_BLUE]
    ns=set(names)
    both=set(v5.LAND_ANY)|set(v5.FETCHES)
    has_g=any(n in v5.LAND_G for n in lands)
    has_u=any(n in v5.LAND_U or n in FLEX_BLUE for n in lands)
    if any(n in both for n in lands):
        has_g=has_u=True
    if 'Lotus Petal' in ns:
        has_g=has_u=True
    if 'Mox Diamond' in ns and len(lands)>=2:
        has_g=has_u=True
    chrome_ok='Chrome Mox' in ns and any(
        n not in base.LANDS and n not in FLEX_BLUE and n not in base.FAST_MANA
        and n not in {'Walking Ballista','Goblin Cannon','Staff of Domination'}
        for n in ns
    )
    if chrome_ok:
        # Chrome can provide the missing color when the imprint pool supports it;
        # treat this as flexible for mulligan screening, not as guaranteed later mana.
        if has_g or has_u:
            has_g=has_u=True
    castable_dorks=sum(n in ONE_G_DORKS for n in names) if has_g else 0
    rocks=sum(n in base.FAST_MANA for n in names if n not in ONE_G_DORKS and n not in base.LANDS)
    sources=len(lands)+castable_dorks+rocks
    return lands,has_g,has_u,sources


def keep_hand_v8(deck, hand, mull_count):
    if deck!='Kinnan':
        return v7._phase_keep(deck, hand, mull_count)
    names=_names(hand); ns=set(names)
    lands,has_g,has_u,sources=_mana_profile(names)
    if not lands:
        return False if mull_count < 4 else sources >= 2

    plan=bool(ns & (base.K_TUTORS | v5.K_ENGINES | v5.K_DRAW | {
        'Basalt Monolith','Grim Monolith','Power Artifact',"Machine God's Effigy",'Devoted Druid',
        'Freed from the Real',"Pemmin's Aura",'Mystic Remora','Rhystic Study'
    }))
    interaction=bool(ns & base.INTERACTION)
    combo_access=bool(ns & (v7.BASALT_TUTORS | v7.EFFIGY_TUTORS | {
        'Basalt Monolith',"Machine God's Effigy",'Devoted Druid','Grim Monolith','Power Artifact'
    }))
    draw=bool(ns & v5.K_DRAW)
    score=sum(base.hand_score('Kinnan',n) for n in names)

    # At seven/six, demand real Simic development. At five, a functional
    # two-source engine/value hand is better than gambling down to four.
    if mull_count == 0:
        return has_g and has_u and sources>=2 and plan and score>=30 and (combo_access or interaction or draw)
    if mull_count == 1:
        return has_g and has_u and sources>=2 and plan and score>=25 and (combo_access or interaction or draw)
    if mull_count == 2:
        return has_g and has_u and sources>=2 and plan and score>=18
    # Four cards or fewer: preserve any genuinely functional hand; do not
    # auto-keep a colorless/blue pile whose green dorks are uncastable.
    return has_g and has_u and sources>=2 and (plan or interaction)


def _keep_priority(name, all_names):
    # London bottoms should preserve functional mana first, then the shortest
    # deterministic line. This deliberately does NOT use base.hand_score,
    # because base gives lands only 3 points and previously bottomed both lands.
    if name in set(v5.LAND_ANY)|set(v5.FETCHES): return 120
    if name in v5.LAND_G or name in v5.LAND_U: return 105
    if name in FLEX_BLUE: return 88
    if name in base.LANDS: return 72
    if name=='Basalt Monolith': return 118
    if name in v7.BASALT_TUTORS: return 110
    if name in {'Kinnan, Bonder Prodigy','Power Artifact','Grim Monolith',"Machine God's Effigy",'Devoted Druid'}: return 102
    if name=='Mystic Remora': return 98
    if name=='Rhystic Study': return 82
    if name in base.INTERACTION: return 90
    if name in ONE_G_DORKS: return 86
    if name in base.FAST_MANA: return 84
    if name in {'Bloom Tender','Incubation Druid','Paradise Druid'}: return 78
    if name in {'Freed from the Real',"Pemmin's Aura"}: return 80
    if name in DIRECT_ACCESS: return 70
    return 30 + base.hand_score('Kinnan',name)


def response_for_v8(prompt, snap, deck, player):
    inp=prompt.get('input',{}) or {}
    typ=inp.get('type')
    if deck=='Kinnan' and typ=='mulliganPutBack':
        hand=base.zone_cards(snap,player,'hand')
        n=int(inp.get('count',inp.get('cardsToReturn',0)) or 0)
        names=_names(hand)
        ranked=sorted(hand,key=lambda c:_keep_priority(base.card_name(c),names))
        ids=[c.get('id') for c in ranked[:n] if c.get('id')]
        return {'type':'mulliganPutBack','output':{'type':'mulliganPutBackDecision','cardIds':ids}}
    return _previous_response(prompt,snap,deck,player)


def target_score_v8(name, snap):
    if v7._is_combo_infinite(snap):
        if name=='Thrasios, Triton Hero': return 10000
        if name=='Staff of Domination': return 9500
        if name=='Walking Ballista': return 200  # do not Kinnan-spin Ballista for X=0
    return _previous_target_score(name,snap)


def action_score_v8(deck, action, snap, player):
    if deck!='Kinnan':
        return v7.v7_action_score(deck,action,snap,player)
    card=v7._card_from_action(action,snap)
    name=base.card_name(card)
    typ=action.get('type','')
    desc=(action.get('description') or '').lower()
    bf=v5._bf_names(snap,player)
    hand=v5._hand_names(snap,player)
    pool=base.mana_total(snap,player)
    own_main=snap.get('activePlayerId')==f'player-{player}' and snap.get('step') in {'main1','main2'}
    infinite={'Kinnan, Bonder Prodigy','Basalt Monolith'} <= bf

    if infinite:
        # Once Kinnan+Basalt exists, stop mindlessly cycling the Monolith.
        # Bank only enough mana for the next productive action.
        if typ=='activateAbility' and name=='Basalt Monolith':
            if pool < 7:
                if 'untap' in desc and pool>=3: return 4200
                if action.get('isManaAbility') or 'add' in desc: return 4190
            return -4000
        if typ=='activateAbility' and name=='Kinnan, Bonder Prodigy':
            return 5000 if pool>=7 else -1500
        if typ=='activateAbility' and name=='Thrasios, Triton Hero':
            return 5200 if pool>=4 else -1500
        if typ=='activateAbility' and name=='Staff of Domination':
            return 5150 if pool>=5 else -1500
        if typ=='activateAbility' and name=='Muddle the Mixture' and 'transmute' in desc and own_main:
            return 5100
        if typ=='cast' and name in {'Thrasios, Triton Hero','Staff of Domination','Walking Ballista'}:
            return 5050
        if typ=='cast' and name=='Muddle the Mixture' and own_main:
            return 4800

    return v7.v7_action_score(deck,action,snap,player)


def deterministic_v8(snap):
    bf_cards=base.zone_cards(snap,0,'battlefield')
    bf={base.card_name(c) for c in bf_cards}
    hand={base.card_name(c) for c in base.zone_cards(snap,0,'hand')}
    if {'Kinnan, Bonder Prodigy','Basalt Monolith'} <= bf:
        # Kinnan can repeatedly inspect successive top-five blocks with infinite
        # colorless mana. If Thrasios is not visible outside the library, it is
        # guaranteed to appear in a finite number of activations; put it onto the
        # battlefield, then infinite C funds Thrasios to draw to Ballista/Staff.
        visible=[]
        for z in snap.get('zones',[]) or []:
            for c in z.get('cards',[]) or []:
                if base.card_name(c)=='Thrasios, Triton Hero':
                    visible.append(z.get('zone'))
        if 'battlefield' in visible:
            return 'Kinnan + Basalt -> infinite C -> Thrasios activation outlet'
        if not visible:
            return 'Kinnan + Basalt -> repeated Kinnan activations -> Thrasios -> draw/deploy library'
        if (bf|hand) & {'Staff of Domination','Walking Ballista'}:
            return 'Kinnan + Basalt + direct colorless outlet'
    return v3.deterministic_kinnan_state.__wrapped__(snap) if hasattr(v3.deterministic_kinnan_state,'__wrapped__') else None


# Install v8 policy after all earlier monkey-patches.
base.keep_hand=keep_hand_v8
base.response_for=response_for_v8
base.action_score=action_score_v8
base.kinnan_target_score=target_score_v8
_v3_old_det=v3.deterministic_kinnan_state

def _det(snap):
    x=deterministic_v8(snap)
    return x or _v3_old_det(snap)
v3.deterministic_kinnan_state=_det


def main():
    if len(sys.argv)<3:
        print('usage: manabrew_pilot_v8.py HARNESS_JAR FORGE_HOME [seed ...]',file=sys.stderr)
        return 2
    jar,home=sys.argv[1],sys.argv[2]
    seeds=[int(x) for x in sys.argv[3:]] or [101,202]
    results=[]
    for seed in seeds:
        try:
            r=v3.run_game(jar,home,seed,max_prompts=1200,max_round=5)
        except Exception as exc:
            r={'seed':seed,'status':'crash','error':repr(exc)}
        print(json.dumps(r,sort_keys=True),flush=True)
        results.append(r)
    (base.RESULT_DIR/'pilot-summary.json').write_text(json.dumps(results,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
