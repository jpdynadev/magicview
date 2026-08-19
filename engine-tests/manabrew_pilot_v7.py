#!/usr/bin/env python3
import json, sys
import manabrew_pilot as base

# Save pristine v1 functions before importing any module that monkey-patches base.
_original_action_score = base.action_score
_original_keep_hand = base.keep_hand

import manabrew_pilot_v3 as v3
import manabrew_pilot_v4  # patches legal chooseColor onto base.response_for
import manabrew_pilot_v5 as v5  # exposes phase-aware policy helpers

BASALT_TUTORS = {
    'Fabricate','Transmute Artifact','Whir of Invention','Trophy Mage','Drift of Phantasms','Moonsilver Key'
}
EFFIGY_TUTORS = {'Fabricate','Transmute Artifact','Whir of Invention'}
FETCH_NAMES = {'Flooded Strand','Misty Rainforest','Polluted Delta','Scalding Tarn','Windswept Heath','Wooded Foothills'}
KNOWN_GOOD_ACTIVATORS = {
    'Basalt Monolith','Grim Monolith','Kinnan, Bonder Prodigy','Staff of Domination','Thrasios, Triton Hero',
    'Moonsilver Key','Tolaria West','Muddle the Mixture','Drift of Phantasms'
}


def _phase_keep(deck, hand, mull_count):
    saved=base.keep_hand
    base.keep_hand=_original_keep_hand
    try:
        return v5.phase_aware_keep(deck,hand,mull_count)
    finally:
        base.keep_hand=saved


def _phase_score(deck, action, snap, player):
    saved=base.action_score
    base.action_score=_original_action_score
    try:
        return v5.phase_aware_action_score(deck,action,snap,player)
    finally:
        base.action_score=saved


def _card_from_action(action, snap):
    cid=action.get('cardId') or action.get('card_id')
    return base.all_visible_cards(snap).get(cid,{})


def _stack_has_targeted_spell_or_ability(snap):
    raw=json.dumps(snap.get('stack',[]) or []).lower()
    return bool(raw) and ('target' in raw)


def _is_combo_infinite(snap):
    bf=v5._bf_names(snap,0)
    if {'Kinnan, Bonder Prodigy','Basalt Monolith'} <= bf: return True
    if {'Grim Monolith','Power Artifact'} <= bf: return True
    if {'Kinnan, Bonder Prodigy','Grim Monolith','Forensic Gadgeteer'} <= bf: return True
    return False


def better_keep_hand(deck, hand, mull_count):
    if deck!='Kinnan':
        return _phase_keep(deck,hand,mull_count)

    names=[base.card_name(c) for c in hand]
    ns=set(names)
    lands=[n for n in names if n in base.LANDS]
    if mull_count < 3 and not lands:
        return False

    # Only count colors that can actually be produced before casting our dorks.
    both=set(v5.LAND_ANY)|set(v5.FETCHES)
    has_g=any(n in v5.LAND_G for n in lands)
    has_u=any(n in v5.LAND_U for n in lands)
    if any(n in both for n in lands): has_g=has_u=True
    if 'Lotus Petal' in ns: has_g=has_u=True
    if 'Mox Diamond' in ns and len(lands)>=2: has_g=has_u=True

    chrome_imprint = 'Chrome Mox' in ns and any(
        n not in base.LANDS and n not in base.FAST_MANA and n not in {'Walking Ballista','Goblin Cannon','Staff of Domination'}
        for n in ns
    )
    if chrome_imprint:
        if has_g and not has_u: has_u=True
        elif has_u and not has_g: has_g=True

    castable_dorks=sum(n in v5.K_DORKS for n in names) if has_g else 0
    unconditional_fast=sum(n in base.FAST_MANA for n in names if n not in v5.K_DORKS)
    sources=len(lands)+castable_dorks+unconditional_fast
    plan=bool(ns & (base.K_TUTORS | v5.K_ENGINES | v5.K_DRAW))
    combo_access=bool(ns & (BASALT_TUTORS | EFFIGY_TUTORS | {'Basalt Monolith',"Machine God's Effigy",'Devoted Druid','Grim Monolith','Power Artifact'}))
    interaction=bool(ns & base.INTERACTION)

    if mull_count>=3:
        return len(lands)>=1 and sources>=2 and (has_g or has_u)
    if not (has_g and has_u): return False
    if sources<2 or not plan: return False
    score=sum(base.hand_score('Kinnan',n) for n in names)
    threshold=34 if mull_count==0 else 28 if mull_count==1 else 23
    return score>=threshold and (combo_access or interaction or bool(ns & v5.K_DRAW))


def v7_action_score(deck, action, snap, player):
    card=_card_from_action(action,snap)
    name=base.card_name(card)
    typ=action.get('type','')
    desc=(action.get('description') or '').lower()
    own_turn=snap.get('activePlayerId')==f'player-{player}'
    own_main=own_turn and snap.get('step') in {'main1','main2'}
    bf=v5._bf_names(snap,player)
    hand=v5._hand_names(snap,player)

    if deck=='Kinnan' and own_main and typ=='cast':
        # Score tutors by the line they complete from this exact board.
        if 'Devoted Druid' in bf and "Machine God's Effigy" not in bf and name in EFFIGY_TUTORS:
            return 2020
        if "Machine God's Effigy" in hand and 'Devoted Druid' not in bf and name in {'Chord of Calling','Worldly Tutor','Finale of Devastation',"Nature's Rhythm","Summoner's Pact"}:
            return 2010
        if 'Kinnan, Bonder Prodigy' in bf and 'Basalt Monolith' not in bf and name in BASALT_TUTORS:
            return 2005
        if 'Devoted Druid' in bf and name=="Machine God's Effigy":
            return 2040
        if 'Kinnan, Bonder Prodigy' in bf and name=='Basalt Monolith':
            return 2030

    if typ=='activateAbility':
        is_mana=bool(action.get('isManaAbility'))
        if is_mana and not _is_combo_infinite(snap):
            return -1700

        if name=='Spellskite':
            return 1850 if _stack_has_targeted_spell_or_ability(snap) else -2500
        if name=='Treasure Vault':
            return 1500 if _is_combo_infinite(snap) else -2400
        if name in FETCH_NAMES and ('search your library' in desc or 'sacrifice' in desc):
            return 2050 if own_main else 800
        if name=='Moonsilver Key':
            return 2025 if 'Kinnan, Bonder Prodigy' in bf and 'Basalt Monolith' not in bf else 1250
        if name in {'Tolaria West','Muddle the Mixture','Drift of Phantasms'} and 'transmute' in desc:
            return 1900 if own_main else -1500
        if name=='Kinnan, Bonder Prodigy':
            return 1900 if _is_combo_infinite(snap) else -500
        if name in {'Staff of Domination','Thrasios, Triton Hero'}:
            return 1950 if _is_combo_infinite(snap) else -600
        if name in {'Basalt Monolith','Grim Monolith'}:
            if _is_combo_infinite(snap): return 2000
            return -500 if 'untap' in desc else -1200
        if name not in KNOWN_GOOD_ACTIVATORS:
            return -1800

    return _phase_score(deck,action,snap,player)


base.keep_hand=better_keep_hand
base.action_score=v7_action_score


def main():
    if len(sys.argv)<3:
        print('usage: manabrew_pilot_v7.py HARNESS_JAR FORGE_HOME [seed ...]',file=sys.stderr)
        return 2
    jar,home=sys.argv[1],sys.argv[2]
    seeds=[int(x) for x in sys.argv[3:]] or [101,202,303]
    results=[]
    for seed in seeds:
        try:
            r=v3.run_game(jar,home,seed,max_prompts=1800,max_round=5)
        except Exception as exc:
            r={'seed':seed,'status':'crash','error':repr(exc)}
        print(json.dumps(r,sort_keys=True),flush=True)
        results.append(r)
    (base.RESULT_DIR/'pilot-summary.json').write_text(json.dumps(results,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
