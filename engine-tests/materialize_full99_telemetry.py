#!/usr/bin/env python3
"""Materialize and validate exactly one explicit record per registered card per valid game."""
from __future__ import annotations
import argparse, collections, glob, hashlib, json
from pathlib import Path

VALID={"game_over","horizon_complete"}
SCHEMA="kinnan-full99-card-telemetry-v2"

def load(path):
    d=json.load(open(path)); return d[0] if isinstance(d,list) else d

def deck_cards(path):
    lines=path.read_text().splitlines(); start=lines.index("[Main]")+1
    cards=[x.split(" ",1)[1].strip() for x in lines[start:] if x.strip()]
    if len(cards)!=99 or len(set(cards))!=99: raise SystemExit(f"{path}: expected 99 unique cards, got {len(cards)}/{len(set(cards))}")
    return cards

def turn(e):
    v=e.get("round")
    return int(v) if isinstance(v,int) or (isinstance(v,str) and v.isdigit()) else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--valid-dir",required=True); ap.add_argument("--telemetry-dir",required=True)
    ap.add_argument("--deck",action="append",required=True,help="VARIANT=PATH")
    ap.add_argument("--out",required=True); ap.add_argument("--coverage",required=True)
    a=ap.parse_args()
    decks={}
    for spec in a.deck:
        v,p=spec.split("=",1); decks[v]=deck_cards(Path(p))
    valid={}
    for p in glob.glob(a.valid_dir+"/**/*.json",recursive=True):
        r=load(p)
        if r.get("status") in VALID:
            k=(str(r.get("variant")),int(r.get("seed")),int(r.get("kinnanSeat")),str(r.get("podProfile")))
            valid[k]=r
    sources={}
    for p in glob.glob(a.telemetry_dir+"/**/*.json",recursive=True):
        r=load(p)
        if r.get("status") in VALID:
            k=(str(r.get("variant")),int(r.get("seed")),int(r.get("kinnanSeat")),str(r.get("podProfile")))
            sources[k]=r
    if set(valid)!=set(sources):
        raise SystemExit(json.dumps({"missingTelemetry":[list(k) for k in sorted(set(valid)-set(sources))],"orphanTelemetry":[list(k) for k in sorted(set(sources)-set(valid))]}))
    rows=[]; per_game={}
    for k in sorted(valid):
        v,seed,seat,pod=k; game=valid[k]; src=sources[k]; cards=decks[v]
        t=src.get("telemetry") or {}; events=t.get("events") or []
        opening=t.get("openingHand") or []; kept=t.get("keptHand") or []
        rejected=set()
        for h in t.get("mulliganHands") or []:
            if not h.get("keep"): rejected.update(h.get("cards") or [])
        putback=set(t.get("putBackCards") or [])
        game_key=f"{seed}:{seat}:{pod}"
        for card in cards:
            ce=[e for e in events if e.get("card")==card or e.get("targetCard")==card or e.get("sourceCard")==card]
            zone=[e for e in events if e.get("kind")=="zoneTransition" and e.get("card")==card]
            draws=[e for e in events if e.get("kind")=="draw" and e.get("card")==card]
            actions=[e for e in events if e.get("kind")=="actionChosen" and e.get("card")==card]
            casts=[e for e in actions if e.get("actionType") in {"cast","play","playLand"}]
            activations=[e for e in actions if e.get("actionType")=="activateAbility"]
            targeted=[e for e in events if e.get("kind")=="targeted" and e.get("targetCard")==card]
            seen=card in opening or card in kept or bool(draws or zone or actions)
            involved=bool(actions or targeted)
            combo_line=str(src.get("comboLine") or "")
            combo=card.lower() in combo_line.lower() if combo_line else False
            essential=bool(combo and src.get("certifiedDeterministicAttempt"))
            first_seen=[x for x in [*(turn(e) for e in draws),*(turn(e) for e in zone),*(turn(e) for e in actions)] if x is not None]
            mana_before=[e.get("manaPool") for e in actions if e.get("manaPool") is not None]
            row={
              "schemaVersion":SCHEMA,"deckHash":src.get("variantDeckSha256"),"variant":v,
              "canonicalKey":game_key,"seed":seed,"seat":seat,"pod":pod,"cardIdentity":card,
              "present":True,"openingHand":card in opening,"kept":card in kept,
              "mulliganed":card in rejected,"putBack":card in putback,
              "seen":seen,"firstSeenTurn":min(first_seen) if first_seen else None,
              "drawn":bool(draws),"firstDrawnTurn":min([turn(e) for e in draws if turn(e) is not None],default=None),
              "zonesByTurn":[{"turn":turn(e),"from":e.get("fromZone"),"to":e.get("toZone")} for e in zone],
              "zoneChanges":zone,"tutored":False,"revealed":False,
              "castOrPlayed":bool(casts),"castOrPlayedTurns":[turn(e) for e in casts],
              "manaProduced":False,"manaSpent":bool(casts or activations),"manaPoolBeforeActions":mana_before,
              "activated":bool(activations),"used":involved,"comboParticipation":combo,
              "protectionParticipation":any(bool(e.get("hasProtection")) for e in casts) or card in set(src.get("protectionAvailable") or []),
              "interactionParticipation":bool(targeted) or any(e.get("kind")=="opponentAction" and e.get("card")==card for e in events),
              "outcomeAttribution":{"merelyPresent":True,"involved":involved,"essential":essential},
              "assemblyT4":(src.get("firstAssemblyTurn") or 99)<=4,
              "attemptT4":(src.get("firstAttemptTurn") or 99)<=4,
              "protectedAttemptT4":bool(src.get("strictProtectedT4")),"naturalWin":bool(src.get("kinnanWon")),
              "packageExecution":involved,"failureCode":src.get("primaryFailureCode")
            }
            rows.append(row)
        per_game[k]=len(cards)
    dup=collections.Counter((r["variant"],r["canonicalKey"],r["cardIdentity"]) for r in rows)
    duplicates=sum(n-1 for n in dup.values() if n>1)
    expected=len(valid)*99; actual=len(rows)
    missing={":".join(map(str,k)):99-per_game.get(k,0) for k in valid if per_game.get(k,0)!=99}
    coverage={"schemaVersion":SCHEMA,"validGames":len(valid),"expectedRows":expected,"actualRows":actual,
              "missingCards":missing,"duplicates":duplicates,"gamesWithExactly99":sum(n==99 for n in per_game.values()),
              "telemetryComplete":actual==expected and not missing and duplicates==0 and all(n==99 for n in per_game.values())}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    with open(a.out,"w") as f:
        for r in rows:f.write(json.dumps(r,separators=(",",":"),ensure_ascii=False)+"\n")
    Path(a.coverage).write_text(json.dumps(coverage,indent=2,sort_keys=True)+"\n")
    print(json.dumps(coverage,indent=2,sort_keys=True))
    if not coverage["telemetryComplete"]: raise SystemExit("FULL99_TELEMETRY_COVERAGE_FAILED")

if __name__=="__main__": main()
