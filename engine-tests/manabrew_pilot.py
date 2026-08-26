#!/usr/bin/env python3
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECK_DIR = ROOT / 'engine-tests' / 'decks'
RESULT_DIR = ROOT / 'engine-tests' / 'results'
RESULT_DIR.mkdir(parents=True, exist_ok=True)

DECKS = [
    ('Kinnan', 'Kinnan_TestB.dck'),
    ('RogSi', 'RogSi_2026.dck'),
    ('Blue Farm', 'Blue_Farm_2026.dck'),
    ('RogThras', 'RogThras_2026.dck'),
]

LANDS = {
    'Ancient Tomb','Barkchannel Pathway','Boseiju, Who Endures','Botanical Sanctum','Breeding Pool','City of Brass',
    'Command Tower','Flooded Strand','Forest','Gaea\'s Cradle','Gemstone Caverns','Gemstone Mine','Island','Mana Confluence',
    'Misty Rainforest','Otawara, Soaring City','Polluted Delta','Rejuvenating Springs','Scalding Tarn','Starting Town',
    'Tolaria West','Treasure Vault','Tropical Island','Urza\'s Saga','Waterlogged Grove','Windswept Heath','Wooded Foothills','Yavimaya Coast',
    'Arid Mesa','Badlands','Blood Crypt','Bloodstained Mire','City of Traitors','Marsh Flats','Phyrexian Tower','Steam Vents',
    'Undercity Sewers','Underground Sea','Verdant Catacombs','Volcanic Island','Watery Grave',
}
FAST_MANA = {
    'Chrome Mox','Mox Diamond','Mox Opal','Mox Amber','Lotus Petal','Mana Vault','Sol Ring','Ancient Tomb',
    'Elvish Spirit Guide','Simian Spirit Guide','Dark Ritual','Cabal Ritual','Rite of Flame','Culling the Weak','Rain of Filth',
    'Arcane Signet','Talisman of Curiosity','Talisman of Dominance','Talisman of Indulgence','Springleaf Drum','Moonsnare Prototype'
}
INTERACTION = {
    'Force of Will','Fierce Guardianship','Pact of Negation','Flusterstorm','Swan Song','An Offer You Can\'t Refuse',
    'Mental Misstep','Mindbreak Trap','Daze','Pyroblast','Red Elemental Blast','Deflecting Swat','Deadly Rollick',
    'Chain of Vapor','Into the Flood Maw','Snap','Veil of Summer','Borne Upon a Wind'
}
K_TUTORS = {'Fabricate','Transmute Artifact','Whir of Invention','Trophy Mage','Muddle the Mixture','Drift of Phantasms','Worldly Tutor','Summoner\'s Pact','Finale of Devastation','Chord of Calling','Neoform','Nature\'s Rhythm','Moonsilver Key','Crop Rotation'}
R_TUTORS = {'Demonic Tutor','Vampiric Tutor','Imperial Seal','Mystical Tutor','Gamble','Diabolic Intent','Grim Tutor','Beseech the Mirror','Demonic Counsel','Wishclaw Talisman','Praetor\'s Grasp'}


def parse_dck(path):
    sec=None; commanders=[]; cards=[]
    for raw in path.read_text().splitlines():
        s=raw.strip()
        if not s: continue
        if s.startswith('[') and s.endswith(']'):
            sec=s.lower(); continue
        if s[0].isdigit() and ' ' in s and sec in ('[commander]','[main]'):
            n,name=s.split(' ',1); name=name.split('|',1)[0].strip()
            if sec=='[commander]': commanders += [name]*int(n)
            cards += [name]*int(n)
    assert len(cards)==100
    return commanders,cards


def rpc(proc,obj):
    proc.stdin.write(json.dumps(obj,separators=(',',':'))+'\n'); proc.stdin.flush()
    line=proc.stdout.readline()
    if not line: raise RuntimeError('harness stdout closed')
    x=json.loads(line)
    if not x.get('ok'): raise RuntimeError(x.get('error'))
    return x.get('result','')


def card_name(c):
    return ((c or {}).get('identity') or {}).get('name','')


def zone_cards(snap, player, zone):
    out=[]
    for z in snap.get('zones',[]):
        if z.get('ownerId')==f'player-{player}' and z.get('zone')==zone:
            out += z.get('cards',[]) or []
    return out


def all_visible_cards(snap):
    m={}
    for z in snap.get('zones',[]):
        for c in z.get('cards',[]) or []:
            m[c.get('id')]=c
    for c in snap.get('stack',[]) or []:
        if isinstance(c,dict) and c.get('id'): m[c['id']]=c
    return m


def battlefield_names(snap, player):
    return {card_name(c) for c in zone_cards(snap,player,'battlefield')}


def mana_total(snap, player):
    p=snap.get('players',[{}]*4)[player]
    return sum((p.get('manaPool') or {}).values())


def hand_score(deck, name):
    if name in LANDS: return 3
    if name in FAST_MANA: return 8
    if name in INTERACTION: return 6
    if deck=='Kinnan':
        vals={
            'Basalt Monolith':14,'Grim Monolith':9,'Power Artifact':10,'Machine God\'s Effigy':8,'Devoted Druid':10,
            'Freed from the Real':8,'Pemmin\'s Aura':8,'Agatha\'s Soul Cauldron':8,'Kinnan, Bonder Prodigy':12,
            'Mystic Remora':8,'Rhystic Study':7,'Staff of Domination':5,'Walking Ballista':5,'Thrasios, Triton Hero':6,
            'Birds of Paradise':7,'Elvish Mystic':7,'Llanowar Elves':7,'Fyndhorn Elves':7,'Bloom Tender':8,'Delighted Halfling':7,
            'Forensic Gadgeteer':7,'Pili-Pala':5,'Horseshoe Crab':5,'Leech Bonder':4,'Incubation Druid':5,'Paradise Druid':4,
        }
        if name in K_TUTORS: return 9
        return vals.get(name,2)
    if deck=='RogSi':
        if name in R_TUTORS: return 10
        vals={'Underworld Breach':12,'Lion\'s Eye Diamond':10,'Brain Freeze':9,'Thassa\'s Oracle':8,'Demonic Consultation':10,
              'Tainted Pact':10,'Ad Nauseam':11,'Necropotence':9,'Mystic Remora':7,'Rhystic Study':7,'Wheel of Fortune':7,
              'Windfall':6,'Yawgmoth\'s Will':8,'Jeska\'s Will':8,'Rograkh, Son of Rohgahh':4}
        return vals.get(name,3)
    if deck=='Blue Farm':
        if name in R_TUTORS: return 9
        vals={'Thassa\'s Oracle':8,'Demonic Consultation':10,'Tainted Pact':10,'Ad Nauseam':9,'Mystic Remora':8,'Rhystic Study':8,
              'Tymna the Weaver':7,'Kraum, Ludevic\'s Opus':5}
        return vals.get(name,3)
    if deck=='RogThras':
        vals={'Thrasios, Triton Hero':8,'Rograkh, Son of Rohgahh':4,'Mystic Remora':8,'Rhystic Study':8}
        return vals.get(name,3)
    return 1


def keep_hand(deck, hand, mull_count):
    names=[card_name(c) for c in hand]
    land=sum(n in LANDS for n in names)
    mana=sum((n in FAST_MANA) or (n in {'Birds of Paradise','Elvish Mystic','Llanowar Elves','Fyndhorn Elves','Delighted Halfling'}) for n in names)
    score=sum(hand_score(deck,n) for n in names)
    if mull_count>=3: return True
    if deck=='Kinnan':
        plan=any(n in K_TUTORS or n in {'Basalt Monolith','Grim Monolith','Power Artifact','Devoted Druid','Machine God\'s Effigy','Freed from the Real','Pemmin\'s Aura','Mystic Remora','Rhystic Study'} for n in names)
        return (land>=1 and land+mana>=2 and plan and score>=34) or score>=43
    if deck=='RogSi':
        plan=any(n in R_TUTORS or n in {'Underworld Breach','Ad Nauseam','Necropotence','Demonic Consultation','Tainted Pact'} for n in names)
        return land>=1 and land+mana>=2 and plan
    return land>=1 and land+mana>=2 and score>=30


def kinnan_target_score(name, snap):
    bf=battlefield_names(snap,0)
    # Completion-aware scoring beats static card quality.
    if 'Devoted Druid' in bf and name=="Machine God's Effigy": return 1000
    if 'Horseshoe Crab' in bf and 'Kinnan, Bonder Prodigy' in bf and name=="Machine God's Effigy": return 930
    if 'Pili-Pala' in bf and 'Kinnan, Bonder Prodigy' in bf and name=="Machine God's Effigy": return 920
    if 'Kinnan, Bonder Prodigy' in bf and name=='Basalt Monolith': return 900
    if {'Kinnan, Bonder Prodigy','Basalt Monolith'} <= bf:
        if name in {'Staff of Domination','Walking Ballista'}: return 880
        if name in {'Stonework Packbeast','Energy Refractor','Agatha\'s Soul Cauldron'}: return 820
    if {'Kinnan, Bonder Prodigy','Grim Monolith','Forensic Gadgeteer'} <= bf:
        if name in {'Staff of Domination','Walking Ballista'}: return 860
    static={
        'Basalt Monolith':120,"Machine God's Effigy":105,'Grim Monolith':90,'Agatha\'s Soul Cauldron':85,
        'Staff of Domination':80,'Walking Ballista':78,'Moonsilver Key':70,'Paradise Mantle':68,'Energy Refractor':62,
        'Stonework Packbeast':60,'Trophy Mage':55,'Devoted Druid':85,'Forensic Gadgeteer':75,'Thrasios, Triton Hero':72,
        'Freed from the Real':82,'Pemmin\'s Aura':82,'Power Artifact':80,
    }
    return static.get(name, hand_score('Kinnan',name))


def generic_target_score(deck,name,snap,player):
    if deck=='Kinnan': return kinnan_target_score(name,snap)
    if deck=='RogSi':
        vals={'Underworld Breach':300,'Demonic Consultation':280,'Tainted Pact':275,'Thassa\'s Oracle':270,'Ad Nauseam':260,
              'Lion\'s Eye Diamond':250,'Brain Freeze':245,'Demonic Tutor':230,'Vampiric Tutor':225,'Mystical Tutor':210}
        return vals.get(name,hand_score(deck,name))
    return hand_score(deck,name)


def choose_card_ids(deck, cards, snap, player, min_n, max_n, prompt_text=''):
    scored=[]
    for c in cards:
        n=card_name(c)
        score=generic_target_score(deck,n,snap,player)
        scored.append((score,c.get('id'),n))
    scored.sort(reverse=True)
    n=max(min_n, min(max_n, max(min_n,1))) if cards else 0
    return [x[1] for x in scored[:n] if x[1]]


def threat_on_stack(snap, player):
    stack=snap.get('stack',[]) or []
    if not stack: return False
    text=' '.join(json.dumps(x) for x in stack).lower()
    words=['thassa','consultation','tainted pact','underworld breach','ad nauseam','finale of devastation','brain freeze','win','target']
    return any(w in text for w in words)


def action_score(deck, action, snap, player):
    cards=all_visible_cards(snap)
    cid=action.get('cardId') or action.get('card_id')
    c=cards.get(cid,{})
    name=card_name(c)
    typ=action.get('type','')
    bf=battlefield_names(snap,player)
    score=-50
    if typ=='cast':
        score=hand_score(deck,name)
        if name in LANDS: score=70 + hand_score(deck,name)
        if name in FAST_MANA: score+=35
        if deck=='Kinnan':
            if name=='Kinnan, Bonder Prodigy': score+=65
            if name in K_TUTORS: score+=45
            if name=='Basalt Monolith' and 'Kinnan, Bonder Prodigy' in bf: score+=300
            if name=="Machine God's Effigy" and 'Devoted Druid' in bf: score+=340
            if name in {'Devoted Druid','Forensic Gadgeteer','Freed from the Real','Pemmin\'s Aura','Power Artifact'}: score+=35
            if name in {'Mystic Remora','Rhystic Study'}: score+=25
        elif deck=='RogSi':
            if name in R_TUTORS: score+=70
            if name in {'Underworld Breach','Ad Nauseam','Necropotence','Demonic Consultation','Tainted Pact','Thassa\'s Oracle'}: score+=80
        elif deck=='Blue Farm':
            if name in {'Tymna the Weaver','Kraum, Ludevic\'s Opus','Mystic Remora','Rhystic Study'}: score+=45
        elif deck=='RogThras':
            if name=='Thrasios, Triton Hero': score+=55
        if snap.get('stack') and name in INTERACTION: score+=220
    elif typ=='activateAbility':
        desc=(action.get('description') or '').lower()
        is_mana=bool(action.get('isManaAbility'))
        score=2
        if deck=='Kinnan':
            # Execute recognized deterministic mana loops when Forge offers the legal abilities.
            if name=='Basalt Monolith' and 'Kinnan, Bonder Prodigy' in bf:
                if ('add' in desc or is_mana) and mana_total(snap,player)<80: score=500
                if 'untap' in desc and mana_total(snap,player)>=3 and mana_total(snap,player)<80: score=510
            if name=='Devoted Druid' and c.get('isCopy') and 'Artifact' in (c.get('types') or []):
                if ('add' in desc or is_mana) and mana_total(snap,player)<80: score=520
                if 'untap' in desc and mana_total(snap,player)<80: score=530
            if name in {'Thrasios, Triton Hero','Staff of Domination'} and mana_total(snap,player)>=8: score=180
            if name=='Kinnan, Bonder Prodigy' and mana_total(snap,player)>=7: score=170
        if snap.get('stack') and name in INTERACTION: score+=220
        if is_mana and score<100: score=-20
    return score


def target_ref_score(deck, ref, snap, player, hostile=False):
    rid=ref.get('id'); kind=ref.get('kind')
    cards=all_visible_cards(snap)
    if kind=='card':
        c=cards.get(rid,{})
        name=card_name(c)
        ctrl=c.get('controllerId')
        if deck=='Kinnan' and not hostile:
            bf=battlefield_names(snap,player)
            if name=='Devoted Druid': return 1000
            if name=='Horseshoe Crab' and 'Kinnan, Bonder Prodigy' in bf: return 900
            if name=='Pili-Pala' and 'Kinnan, Bonder Prodigy' in bf: return 890
            if name=='Basalt Monolith': return 700
        if hostile:
            if ctrl!=f'player-{player}':
                return 100 + (50 if name in {'Thassa\'s Oracle','Kinnan, Bonder Prodigy','Underworld Breach','Tymna the Weaver','Kraum, Ludevic\'s Opus'} else 0)
            return -100
        return 30 if ctrl==f'player-{player}' else 0
    if kind=='player': return 10 if rid!=f'player-{player}' else 0
    if kind=='spell': return 100
    return 0


def response_for(prompt, snap, deck, player):
    inp=prompt.get('input',{})
    typ=inp.get('type')
    if typ=='revealCards': return {'type':'revealCards','output':{}}
    if typ=='diceRolled': return {'type':'diceRolled','output':{}}
    if typ=='mulligan':
        hand=zone_cards(snap,player,'hand')
        keep=keep_hand(deck,hand,int(inp.get('mulliganCount',0)))
        return {'type':'mulligan','output':{'type':'mulliganDecision','keep':keep}}
    if typ=='mulliganPutBack':
        hand=zone_cards(snap,player,'hand')
        n=int(inp.get('count', inp.get('cardsToReturn',0)) or 0)
        ranked=sorted(hand,key=lambda c:hand_score(deck,card_name(c)))
        ids=[c.get('id') for c in ranked[:n] if c.get('id')]
        return {'type':'mulliganPutBack','output':{'type':'mulliganPutBackDecision','cardIds':ids}}
    if typ=='chooseAction':
        acts=inp.get('actions',[]) or []
        if not acts: return {'type':'chooseAction','output':{'type':'pass','exhaustStack':False}}
        scored=[(action_score(deck,a,snap,player),a) for a in acts]
        scored.sort(key=lambda x:x[0],reverse=True)
        best_score,best=scored[0]
        # On an opponent's stack, interact only when the offered action is actually useful; otherwise pass.
        if snap.get('stack') and not threat_on_stack(snap,player) and best_score<150:
            return {'type':'chooseAction','output':{'type':'pass','exhaustStack':False}}
        if best_score<=0:
            return {'type':'chooseAction','output':{'type':'pass','exhaustStack':False}}
        return {'type':'chooseAction','output':{'type':'act','actionId':best['id']}}
    if typ=='payManaCost':
        if inp.get('canConfirmFromPool'):
            return {'type':'payManaCost','output':{'type':'pay','auto':True}}
        acts=inp.get('actions',[]) or []
        if acts:
            # Prefer colored producers, then any advertised legal mana action.
            def ps(a):
                s=json.dumps(a)
                return (5 if any(x in s for x in ['"U"','"G"','"B"','"R"','"W"']) else 0) + (2 if 'activateManaAbility' in s else 0)
            a=max(acts,key=ps)
            return {'type':'payManaCost','output':{'type':'act','actionId':a['id']}}
        return {'type':'payManaCost','output':{'type':'cancel'}}
    if typ=='chooseCards':
        cards=inp.get('cards',[]) or []
        ids=choose_card_ids(deck,cards,snap,player,int(inp.get('min',0)),int(inp.get('max',0)),json.dumps(inp.get('presentation',{})))
        return {'type':'chooseCards','output':{'type':'chooseCardsDecision','chosenCardIds':ids}}
    if typ=='chooseBoardTargets':
        cand=inp.get('candidates',[]) or []
        hostile=bool(inp.get('hostile'))
        mx=max(1,int(inp.get('maxTargets',1))); mn=int(inp.get('minTargets',1))
        scored=sorted(((target_ref_score(deck,r,snap,player,hostile),r) for r in cand),key=lambda x:x[0],reverse=True)
        chosen=[r for s,r in scored[:mx] if s>=0]
        if len(chosen)<mn: chosen=[r for _,r in scored[:mn]]
        return {'type':'chooseBoardTargets','output':{'type':'boardTargets','chosen':chosen}}
    if typ=='chooseBoolean':
        return {'type':'chooseBoolean','output':{'type':'booleanDecision','value':True}}
    if typ=='chooseFromSelection':
        opts=inp.get('options',[]) or []
        return {'type':'chooseFromSelection','output':{'type':'selectionDecision','chosenIndices':[0] if opts else []}}
    if typ=='chooseColor':
        # Kinnan prefers U for aura/untap lines, otherwise choose first advertised color.
        avail=inp.get('availableColors') or inp.get('colors') or ['U']
        col='U' if deck=='Kinnan' and 'U' in avail else (avail[0] if avail else 'U')
        return {'type':'chooseColor','output':{'type':'colorDecision','chosenColors':{col:1}}}
    if typ=='chooseNumber':
        hi=int(inp.get('max', inp.get('maximum',0)) or 0)
        lo=int(inp.get('min', inp.get('minimum',0)) or 0)
        return {'type':'chooseNumber','output':{'type':'numberDecision','chosenNumber':hi if hi else lo}}
    if typ=='scry':
        cards=inp.get('cards',[]) or []
        ids=[c.get('id') for c in cards if c.get('id')]
        return {'type':'scry','output':{'type':'scryDecision','zoneCardIds':[ids,[]]}}
    if typ=='reorder':
        items=inp.get('items',[]) or []
        ids=[x.get('id') for x in items if isinstance(x,dict) and x.get('id')]
        return {'type':'reorder','output':{'type':'reorderDecision','orderedIds':ids}}
    if typ=='chooseAttackers':
        return {'type':'chooseAttackers','output':{'type':'attackers','assignments':[]}}
    if typ=='chooseBlockers':
        return {'type':'chooseBlockers','output':{'type':'blockers','assignments':[]}}
    if typ=='chooseDamageAssignmentOrder':
        ids=inp.get('blockerIds',[]) or []
        return {'type':'chooseDamageAssignmentOrder','output':{'type':'damageAssignmentOrder','orderedBlockerIds':ids}}
    if typ=='chooseCombatDamageAssignment':
        return {'type':'chooseCombatDamageAssignment','output':{'type':'combatDamageAssignment','assignments':[]}}
    if typ=='gameOver': return None
    raise RuntimeError(f'unsupported prompt type {typ}: {json.dumps(inp)[:1200]}')


def deterministic_kinnan_state(snap):
    bf_cards=zone_cards(snap,0,'battlefield')
    names={card_name(c) for c in bf_cards}
    # Fully resolved board-state deterministic engines; opponent priority still matters before this state is counted.
    if {'Kinnan, Bonder Prodigy','Basalt Monolith'} <= names:
        outlet = bool(names & {'Staff of Domination','Thrasios, Triton Hero','Stonework Packbeast','Energy Refractor','Agatha\'s Soul Cauldron'})
        hand={card_name(c) for c in zone_cards(snap,0,'hand')}
        outlet = outlet or bool(hand & {'Walking Ballista','Staff of Domination','Thrasios, Triton Hero','Stonework Packbeast','Energy Refractor','Agatha\'s Soul Cauldron'})
        if outlet: return 'Kinnan + Basalt + deterministic outlet'
    # Effigy copies Devoted Druid but becomes a noncreature artifact; identify the copy structurally.
    has_effigy_druid=any(card_name(c)=='Devoted Druid' and c.get('isCopy') and 'Artifact' in (c.get('types') or []) for c in bf_cards)
    if has_effigy_druid and 'Kinnan, Bonder Prodigy' in names:
        return 'Machine God\'s Effigy(copy Devoted Druid) + Kinnan'
    return None


def build_players():
    out=[]
    for name,fn in DECKS:
        commanders,cards=parse_dck(DECK_DIR/fn)
        out.append({'name':name,'commanderNames':commanders,'deck':[{'name':c} for c in cards],'ai':False})
    return out


def run_game(jar, forge_home, seed, max_prompts=5000):
    trace=[]; errors=[]
    proc=subprocess.Popen(['java','-Xmx4g','-jar',jar,'--interactive-server','--forge-home',forge_home],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        payload={'gameId':f'cedh-{seed}','variant':'Commander','startingLife':40,'seed':seed,'players':build_players()}
        start=json.loads(rpc(proc,{'command':'startGame','payload':json.dumps(payload,separators=(',',':'))}))
        sid=start['sessionId']; seen={i:None for i in range(4)}
        result={'seed':seed,'status':'prompt_limit','winner':None,'deterministicKinnan':None,'turn':None,'prompts':0}
        for step in range(max_prompts):
            progressed=False
            for p,(deck,_) in enumerate(DECKS):
                raw=rpc(proc,{'command':'getPrompt','sessionId':sid,'playerIndex':p})
                if not raw: continue
                prompt=json.loads(raw)
                pid=prompt.get('promptId')
                if seen[p]==pid: continue
                seen[p]=pid; progressed=True; result['prompts']+=1
                snap=json.loads(rpc(proc,{'command':'getSnapshot','sessionId':sid,'viewer':p}))
                result['turn']=snap.get('turn')
                kline=deterministic_kinnan_state(snap)
                if kline and not result['deterministicKinnan']:
                    result['deterministicKinnan']={'turn':snap.get('turn'),'line':kline}
                typ=(prompt.get('input') or {}).get('type')
                trace.append({'step':step,'player':p,'deck':deck,'promptId':pid,'type':typ,'turn':snap.get('turn'),'stepName':snap.get('step')})
                if typ=='gameOver':
                    result['status']='game_over'; result['gameOverPrompt']=prompt.get('input');
                    (RESULT_DIR/f'pilot-trace-{seed}.json').write_text(json.dumps(trace,indent=2))
                    return result
                try:
                    ans=response_for(prompt,snap,deck,p)
                except Exception as e:
                    errors.append({'player':p,'prompt':prompt,'error':repr(e)})
                    result['status']='unsupported_prompt'; result['error']=repr(e)
                    (RESULT_DIR/f'pilot-errors-{seed}.json').write_text(json.dumps(errors,indent=2))
                    (RESULT_DIR/f'pilot-trace-{seed}.json').write_text(json.dumps(trace,indent=2))
                    return result
                if ans is not None:
                    rpc(proc,{'command':'submitAction','sessionId':sid,'action':json.dumps(ans,separators=(',',':'))})
            if not progressed:
                time.sleep(0.01)
        (RESULT_DIR/f'pilot-trace-{seed}.json').write_text(json.dumps(trace,indent=2))
        return result
    finally:
        try: proc.terminate(); proc.wait(timeout=3)
        except Exception: proc.kill()
        err=proc.stderr.read() if proc.stderr else ''
        if err: (RESULT_DIR/f'pilot-stderr-{seed}.log').write_text(err)


def main():
    if len(sys.argv)<3:
        print('usage: manabrew_pilot.py HARNESS_JAR FORGE_HOME [seed ...]',file=sys.stderr); return 2
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
