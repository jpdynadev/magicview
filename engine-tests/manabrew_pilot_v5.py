#!/usr/bin/env python3
import json, sys
import manabrew_pilot as base
import manabrew_pilot_v3 as v3
import manabrew_pilot_v4  # applies legal chooseColor patch onto base.response_for

# Preserve v4's color-safe response function before adding phase-aware choice policy.
_color_safe_response_for = base.response_for

K_DORKS = {'Birds of Paradise','Bloom Tender','Delighted Halfling','Devoted Druid','Elvish Mystic','Fyndhorn Elves','Llanowar Elves','Paradise Druid','Incubation Druid'}
K_OUTLETS = {'Walking Ballista','Goblin Cannon','Staff of Domination','Prophet of Distortion','Thrasios, Triton Hero','Energy Refractor','Stonework Packbeast'}
K_DRAW = {'Mystic Remora','Rhystic Study'}
K_ENGINES = {'Basalt Monolith','Grim Monolith','Power Artifact',"Machine God's Effigy",'Agatha\'s Soul Cauldron','Freed from the Real',"Pemmin's Aura",'Cryptolith Rite','Paradise Mantle','Forensic Gadgeteer','Horseshoe Crab','Pili-Pala','Leech Bonder'}

LAND_ANY = {
    'Breeding Pool','City of Brass','Command Tower','Gemstone Mine','Mana Confluence','Rejuvenating Springs','Tropical Island','Waterlogged Grove','Yavimaya Coast','Botanical Sanctum','Barkchannel Pathway','Starting Town'
}
FETCHES = {'Flooded Strand','Misty Rainforest','Polluted Delta','Scalding Tarn','Windswept Heath','Wooded Foothills'}
LAND_G = {'Forest','Gaea\'s Cradle','Boseiju, Who Endures'} | LAND_ANY | FETCHES
LAND_U = {'Island','Otawara, Soaring City'} | LAND_ANY | FETCHES


def _names(cards):
    return {base.card_name(c) for c in cards}


def _hand_names(snap, p):
    return _names(base.zone_cards(snap,p,'hand'))


def _bf_names(snap,p):
    return _names(base.zone_cards(snap,p,'battlefield'))


def _grave_names(snap,p):
    return _names(base.zone_cards(snap,p,'graveyard'))


def _infinite_kinnan(snap):
    bf=_bf_names(snap,0)
    if {'Kinnan, Bonder Prodigy','Basalt Monolith'} <= bf:
        return True
    if {'Grim Monolith','Power Artifact'} <= bf:
        return True
    if {'Kinnan, Bonder Prodigy','Grim Monolith','Forensic Gadgeteer'} <= bf:
        return True
    # Effigy-copy recognition is handled more precisely by v3's deterministic checker.
    return False


def _stack_text(snap):
    return json.dumps(snap.get('stack',[]) or []).lower()


def _stack_has_oracle(snap):
    return "thassa's oracle" in _stack_text(snap) or 'thassa\'s oracle' in _stack_text(snap)


def _stack_is_real_threat(snap, player):
    text=_stack_text(snap)
    if not text:
        return False
    win_markers=["thassa's oracle",'demonic consultation','tainted pact','underworld breach','brain freeze','ad nauseam','final fortune']
    if any(x in text for x in win_markers):
        return True
    # If another player has put an answer on top of our own spell/ability, allow protection.
    if len(snap.get('stack',[]) or []) >= 2:
        return True
    return False


def _functional_kinnan_keep(hand, mull_count):
    names=[base.card_name(c) for c in hand]
    ns=set(names)
    lands=[n for n in names if n in base.LANDS]
    land_count=len(lands)
    if mull_count < 2 and land_count == 0:
        return False

    # Color access for Kinnan. Lotus Petal counts as either; Chrome Mox counts only if
    # a colored nonartifact spell exists to imprint, but we conservatively count it as one color source.
    g=any(n in LAND_G for n in lands) or 'Lotus Petal' in ns
    u=any(n in LAND_U for n in lands) or 'Lotus Petal' in ns
    chrome='Chrome Mox' in ns and any(n not in base.LANDS and n not in base.FAST_MANA and n not in {'Walking Ballista','Goblin Cannon','Staff of Domination'} for n in ns)
    if chrome:
        # Chrome can cover one missing Kinnan color, not both.
        if g and not u: u=True
        elif u and not g: g=True

    accel=sum(n in base.FAST_MANA or n in K_DORKS for n in names)
    mana_sources=land_count+accel
    plan=bool(ns & (base.K_TUTORS | K_ENGINES | K_DRAW))
    interaction=bool(ns & base.INTERACTION)

    if mull_count >= 3:
        return land_count>=1 and (g or u) and mana_sources>=2
    if not (g and u):
        # One-color hands are keepable only with enough selection/acceleration to find the other color.
        if not (land_count>=2 and mana_sources>=3 and plan):
            return False
    if mana_sources < 2:
        return False
    if not plan:
        return False
    # 7-card hands need a strong engine/tutor/draw plan; at 6/5 we loosen slightly.
    score=sum(base.hand_score('Kinnan',n) for n in names)
    threshold=35 if mull_count==0 else 29 if mull_count==1 else 24
    return score>=threshold or (interaction and score>=threshold-3)


def phase_aware_keep(deck, hand, mull_count):
    if deck=='Kinnan':
        return _functional_kinnan_keep(hand,mull_count)
    names=[base.card_name(c) for c in hand]
    land=sum(n in base.LANDS for n in names)
    fast=sum(n in base.FAST_MANA for n in names)
    if mull_count<2 and land==0:
        return False
    if land+fast<2:
        return mull_count>=3
    if deck=='RogSi':
        plan=any(n in base.R_TUTORS or n in {'Underworld Breach','Ad Nauseam','Necropotence','Demonic Consultation','Tainted Pact','Mystic Remora','Rhystic Study'} for n in names)
        return plan or mull_count>=2
    return base.keep_hand(deck,hand,mull_count)


def _card_from_action(action,snap):
    cid=action.get('cardId') or action.get('card_id')
    return base.all_visible_cards(snap).get(cid,{})


def _is_land_play(action, card):
    return action.get('type')=='cast' and ((action.get('label') or '').startswith('Play ') or base.card_name(card) in base.LANDS)


def _base_or_minus(deck, action, snap, player):
    try:
        return base.action_score(deck,action,snap,player)
    except Exception:
        return -100


def phase_aware_action_score(deck, action, snap, player):
    card=_card_from_action(action,snap)
    name=base.card_name(card)
    typ=action.get('type','')
    own_turn=snap.get('activePlayerId')==f'player-{player}'
    main=snap.get('step') in {'main1','main2'}
    own_main=own_turn and main
    stack_threat=_stack_is_real_threat(snap,player)
    bf=_bf_names(snap,player)
    hand=_hand_names(snap,player)

    # Always make land drops before proactive spells in our own main phase.
    if _is_land_play(action,card):
        return 2000 if own_main else -2000

    # Off-turn / non-main: only real interaction, protection, or an already-assembled engine.
    if not own_main:
        if typ=='cast' and name in base.INTERACTION:
            return 1800 if stack_threat else -1500
        if deck in {'RogSi','Blue Farm'} and name in {'Demonic Consultation','Tainted Pact'} and _stack_has_oracle(snap):
            return 1900
        if typ=='activateAbility' and deck=='Kinnan':
            if _infinite_kinnan(snap) and name in {'Basalt Monolith','Grim Monolith','Kinnan, Bonder Prodigy','Staff of Domination','Thrasios, Triton Hero'}:
                return 1700
        return -1500

    # From here on, proactive play is allowed because it is our own main phase.
    if deck=='Kinnan':
        infinite=_infinite_kinnan(snap)
        if typ=='cast':
            if name in base.FAST_MANA:
                return 1500
            if name=='Kinnan, Bonder Prodigy':
                return 1450
            if name=="Machine God's Effigy" and 'Devoted Druid' in bf:
                return 1950
            if name=='Devoted Druid' and "Machine God's Effigy" in (bf|hand):
                return 1750
            if name=='Basalt Monolith' and 'Kinnan, Bonder Prodigy' in bf:
                return 1900
            if name=='Power Artifact' and 'Grim Monolith' in bf:
                return 1880
            if name in K_OUTLETS:
                return 1800 if infinite else 40
            if name in K_DRAW:
                return 1200
            if name in base.K_TUTORS:
                # Pact is a win-now tutor, not generic setup; avoid the delayed upkeep liability.
                if name=="Summoner's Pact":
                    if ("Machine God's Effigy" in (bf|hand) and 'Devoted Druid' not in bf):
                        return 1550
                    return 150
                return 1100
            if name in K_ENGINES:
                return 1050
            if name in K_DORKS:
                return 900
            if name in base.INTERACTION:
                return 1700 if stack_threat else 100
            return _base_or_minus(deck,action,snap,player)
        if typ=='activateAbility':
            if infinite and name in {'Basalt Monolith','Grim Monolith','Kinnan, Bonder Prodigy','Staff of Domination','Thrasios, Triton Hero'}:
                return 1850
            return _base_or_minus(deck,action,snap,player)

    if deck=='RogSi':
        if typ=='cast':
            if name in base.FAST_MANA: return 1500
            if name in base.R_TUTORS: return 1200
            if name in {'Mystic Remora','Rhystic Study','Necropotence'}: return 1050
            if name=='Ad Nauseam': return 1400
            if name=="Thassa's Oracle":
                return 1750 if ({'Demonic Consultation','Tainted Pact'} & hand) else 100
            if name in {'Demonic Consultation','Tainted Pact'}:
                return 1800 if ("Thassa's Oracle" in bf or _stack_has_oracle(snap)) else -200
            if name=='Underworld Breach':
                grave=_grave_names(snap,player)
                pieces=(hand|grave)
                return 1650 if {'Lion\'s Eye Diamond','Brain Freeze'} <= pieces else 800
            if name in base.INTERACTION: return 1750 if stack_threat else 80
            return _base_or_minus(deck,action,snap,player)

    if deck=='Blue Farm':
        if typ=='cast':
            if name in base.FAST_MANA: return 1500
            if name in base.R_TUTORS: return 1150
            if name in {'Mystic Remora','Rhystic Study','Tymna the Weaver','Kraum, Ludevic\'s Opus'}: return 1100
            if name=="Thassa's Oracle": return 1700 if ({'Demonic Consultation','Tainted Pact'} & hand) else 100
            if name in {'Demonic Consultation','Tainted Pact'}: return 1800 if ("Thassa's Oracle" in bf or _stack_has_oracle(snap)) else -200
            if name in base.INTERACTION: return 1750 if stack_threat else 80
            return _base_or_minus(deck,action,snap,player)

    # RogThras / generic seat: no proactive off-turn casts, but retain reasonable main-phase engine development.
    if typ=='cast' and name in base.INTERACTION:
        return 1700 if stack_threat else 80
    return _base_or_minus(deck,action,snap,player)


base.keep_hand = phase_aware_keep
base.action_score = phase_aware_action_score


def main():
    if len(sys.argv)<3:
        print('usage: manabrew_pilot_v5.py HARNESS_JAR FORGE_HOME [seed ...]',file=sys.stderr)
        return 2
    jar,home=sys.argv[1],sys.argv[2]
    seeds=[int(x) for x in sys.argv[3:]] or [101,202,303]
    results=[]
    for seed in seeds:
        try: r=v3.run_game(jar,home,seed,max_prompts=1800,max_round=5)
        except Exception as exc: r={'seed':seed,'status':'crash','error':repr(exc)}
        print(json.dumps(r,sort_keys=True),flush=True); results.append(r)
    (base.RESULT_DIR/'pilot-summary.json').write_text(json.dumps(results,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
