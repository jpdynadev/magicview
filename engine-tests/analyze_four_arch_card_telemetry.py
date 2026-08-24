#!/usr/bin/env python3
"""Aggregate four-architecture strict paired simulation + card telemetry."""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import math
from pathlib import Path
from typing import Any

VALID = {"game_over", "horizon_complete"}


def load_json(path: str) -> dict[str, Any]:
    d = json.load(open(path))
    return d[0] if isinstance(d, list) and d else d


def deck_cards(path: Path) -> list[str]:
    lines = path.read_text().splitlines(); start = lines.index("[Main]") + 1
    return [line.split(" ", 1)[1].strip() for line in lines[start:] if line.strip()]


def key(r):
    return (int(r["seed"]), int(r["kinnanSeat"]), str(r.get("podProfile")))


def endpoint(r, metric):
    if metric == "assemblyT4": return (r.get("firstAssemblyTurn") or 99) <= 4
    if metric == "attemptT4": return (r.get("firstAttemptTurn") or 99) <= 4
    if metric == "protectedT4": return bool(r.get("strictProtectedT4"))
    if metric == "win": return bool(r.get("kinnanWon"))
    raise KeyError(metric)


def mcnemar(base, cand, common, metric):
    a = sum(endpoint(cand[k], metric) and not endpoint(base[k], metric) for k in common)
    c = sum(endpoint(base[k], metric) and not endpoint(cand[k], metric) for k in common)
    n = a + c
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(a, c) + 1)) / (2 ** n))
    return {"candidateOnly": a, "baselineOnly": c, "pTwoSided": p}


def first_round(events, kinds, card):
    vals=[]
    for e in events:
        if e.get("kind") in kinds and e.get("card") == card:
            v=e.get("round")
            if isinstance(v,int): vals.append(v)
    return min(vals) if vals else None


def game_card_features(game, card):
    t=game.get("telemetry") or {}; events=t.get("events") or []
    opening=set(t.get("openingHand") or []); kept=set(t.get("keptHand") or [])
    rejected=any(card in set(x.get("cards") or []) for x in (t.get("mulliganHands") or []) if not x.get("keep"))
    putback=card in set(t.get("putBackCards") or [])
    draws=[e for e in events if e.get("kind")=="draw" and e.get("card")==card]
    actions=[e for e in events if e.get("kind")=="actionChosen" and e.get("card")==card]
    casts=[e for e in actions if e.get("actionType") in {"cast","playLand","play"}]
    activations=[e for e in actions if e.get("actionType")=="activateAbility"]
    targeted=[e for e in events if e.get("kind")=="targeted" and e.get("targetCard")==card and e.get("hostile")]
    zone=[e for e in events if e.get("kind")=="zoneTransition" and e.get("card")==card]
    seen=card in opening or card in kept or bool(draws) or bool(actions) or bool(zone)
    with_prot=any(bool(e.get("hasProtection")) for e in casts)
    hand_context=collections.Counter()
    source_context=collections.Counter()
    for e in casts:
        for other in e.get("handBefore") or []:
            if other != card: hand_context[other]+=1
    for e in targeted:
        src=e.get("sourceCard") or "UNKNOWN"
        source_context[str(src)]+=1
    return {
        "opening":card in opening,"kept":card in kept,"rejected":rejected,"putBack":putback,
        "drawn":bool(draws),"seen":seen,"actions":len(actions),"castOrPlay":bool(casts),
        "activations":len(activations),"targetedEvents":len(targeted),"targeted":bool(targeted),
        "playedWithProtection":with_prot,"firstDrawRound":first_round(events,{"draw"},card),
        "firstActionRound":first_round(events,{"actionChosen"},card),
        "actionRounds":collections.Counter(e.get("round") for e in actions if isinstance(e.get("round"),int)),
        "handContext":hand_context,"sourceContext":source_context,
    }


def safe_rate(n,d): return (n/d) if d else None


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--all",required=True); ap.add_argument("--deck-dir",default="engine-tests/decks"); ap.add_argument("--out",required=True); args=ap.parse_args()
    variants=["F10","TOURNAMENT_SIEGE_2026_LOGAN","DORKMAX_F10","NODEMAX_F10"]
    deck_files={v:("Kinnan_ARCH_F10.dck" if v=="F10" else f"Kinnan_ARCH_{v}.dck") for v in variants}
    rows={v:[] for v in variants}; telemetry={v:[] for v in variants}; errors={v:[] for v in variants}
    for p in glob.glob(f"{args.all}/**/valid/*.json",recursive=True):
        try:r=load_json(p)
        except Exception:continue
        if r.get("variant") in rows: rows[r["variant"]].append(r)
    for p in glob.glob(f"{args.all}/**/card-telemetry/*.json",recursive=True)+glob.glob(f"{args.all}/**/telemetry/*.json",recursive=True):
        try:r=load_json(p)
        except Exception:continue
        if r.get("variant") in telemetry: telemetry[r["variant"]].append(r)
    for p in glob.glob(f"{args.all}/**/*errors.ndjson",recursive=True):
        for line in open(p):
            try:r=json.loads(line)
            except Exception:continue
            if r.get("variant") in errors: errors[r["variant"]].append(r)
    maps={v:{key(r):r for r in rows[v] if r.get("status") in VALID and r.get("pilotVersion")=="arch-aware-v1.16-adversarial"} for v in variants}
    tmaps={v:{key(r):r for r in telemetry[v] if r.get("status") in VALID and r.get("pilotVersion")=="arch-aware-v1.16-adversarial"} for v in variants}
    base=maps["F10"]
    report={"schema":"kinnan-four-architecture-card-telemetry-v1","strictValid":False,"variants":{},"paired":{},"cardAnalytics":{},"errorAttempts":{},"telemetryCoverage":{}}
    for v in variants:
        good=list(maps[v].values())
        report["variants"][v]={
            "records":len(rows[v]),"valid":len(good),"uniqueKeys":len(maps[v]),
            "deckHashes":sorted(set(str(r.get("variantDeckSha256")) for r in good)),
            "assemblyT4":sum(endpoint(r,"assemblyT4") for r in good),
            "attemptT4":sum(endpoint(r,"attemptT4") for r in good),
            "protectedT4":sum(endpoint(r,"protectedT4") for r in good),
            "wins":sum(endpoint(r,"win") for r in good),
            "mulligans":sum(int(r.get("mulligans") or 0) for r in good),
            "failureCodes":dict(collections.Counter(str(r.get("primaryFailureCode") or "NONE") for r in good)),
            "pods":{},"seats":{},
        }
        for pod in ("balanced","turbo","midrange","mixed"):
            x=[r for r in good if r.get("podProfile")==pod]
            report["variants"][v]["pods"][pod]={"n":len(x),"assemblyT4":sum(endpoint(r,"assemblyT4") for r in x),"attemptT4":sum(endpoint(r,"attemptT4") for r in x),"protectedT4":sum(endpoint(r,"protectedT4") for r in x),"wins":sum(endpoint(r,"win") for r in x)}
        for s in range(4):
            x=[r for r in good if int(r.get("kinnanSeat",-1))==s]
            report["variants"][v]["seats"][str(s)]={"n":len(x),"assemblyT4":sum(endpoint(r,"assemblyT4") for r in x),"attemptT4":sum(endpoint(r,"attemptT4") for r in x),"protectedT4":sum(endpoint(r,"protectedT4") for r in x),"wins":sum(endpoint(r,"win") for r in x)}
        report["errorAttempts"][v]=dict(collections.Counter(str(e.get("status") or "missing") for e in errors[v]))
        report["telemetryCoverage"][v]={"records":len(tmaps[v]),"matchingValidKeys":len(set(tmaps[v]) & set(maps[v]))}
        if v!="F10":
            common=sorted(set(base)&set(maps[v])); p={"keys":len(common)}
            for metric in ("assemblyT4","attemptT4","protectedT4","win"):
                cv=sum(endpoint(maps[v][k],metric) for k in common); bv=sum(endpoint(base[k],metric) for k in common)
                p[metric]={"candidate":cv,"baseline":bv,"deltaRate":safe_rate(cv-bv,len(common)),**mcnemar(base,maps[v],common,metric)}
            report["paired"][v]=p

    deckdir=Path(args.deck_dir)
    csv_rows=[]
    for v in variants:
        cards=deck_cards(deckdir/deck_files[v]); games=[tmaps[v][k] for k in sorted(set(tmaps[v]) & set(maps[v]))]
        card_report={}
        for card in cards:
            counts=collections.Counter(); rounds=collections.Counter(); handctx=collections.Counter(); sources=collections.Counter(); seen_pt4=seen_wins=notseen_pt4=notseen_n=played_pt4=played_n=0; first_action=[]; first_draw=[]
            for g in games:
                f=game_card_features(g,card); pt4=bool(g.get("strictProtectedT4")); win=bool(g.get("kinnanWon"))
                for name in ("opening","kept","rejected","putBack","drawn","seen","castOrPlay","targeted","playedWithProtection"):
                    counts[name]+=int(bool(f[name]))
                counts["actions"]+=f["actions"]; counts["activations"]+=f["activations"]; counts["targetedEvents"]+=f["targetedEvents"]
                rounds.update(f["actionRounds"]); handctx.update(f["handContext"]); sources.update(f["sourceContext"])
                if f["firstActionRound"] is not None:first_action.append(f["firstActionRound"])
                if f["firstDrawRound"] is not None:first_draw.append(f["firstDrawRound"])
                if f["seen"]: seen_pt4+=int(pt4); seen_wins+=int(win)
                else: notseen_pt4+=int(pt4); notseen_n+=1
                if f["castOrPlay"]: played_n+=1; played_pt4+=int(pt4)
            n=len(games); seen=counts["seen"]
            item={
                "games":n,"openingHandGames":counts["opening"],"keptHandGames":counts["kept"],"mulliganRejectedGames":counts["rejected"],"putBackGames":counts["putBack"],"drawnGames":counts["drawn"],"seenGames":seen,
                "actionEvents":counts["actions"],"playedGames":counts["castOrPlay"],"activationEvents":counts["activations"],"hostileTargetedGames":counts["targeted"],"hostileTargetEvents":counts["targetedEvents"],
                "playedWithProtectionGames":counts["playedWithProtection"],"playedWithProtectionRate":safe_rate(counts["playedWithProtection"],counts["castOrPlay"]),
                "strictProtectedWhenSeen":seen_pt4,"strictProtectedRateWhenSeen":safe_rate(seen_pt4,seen),"strictProtectedRateWhenNotSeen":safe_rate(notseen_pt4,notseen_n),
                "seenProtectedDelta":(safe_rate(seen_pt4,seen)-safe_rate(notseen_pt4,notseen_n)) if seen and notseen_n else None,
                "strictProtectedWhenPlayed":played_pt4,"strictProtectedRateWhenPlayed":safe_rate(played_pt4,played_n),"winsWhenSeen":seen_wins,
                "avgFirstActionRound":safe_rate(sum(first_action),len(first_action)),"avgFirstDrawRound":safe_rate(sum(first_draw),len(first_draw)),
                "actionRoundHistogram":{str(k):v for k,v in sorted(rounds.items())},"topHandContext":handctx.most_common(12),"interactionSources":sources.most_common(12),
            }
            card_report[card]=item
            csv_rows.append({"variant":v,"card":card,**{k:item[k] for k in ("games","openingHandGames","keptHandGames","mulliganRejectedGames","putBackGames","drawnGames","seenGames","playedGames","playedWithProtectionRate","hostileTargetedGames","strictProtectedRateWhenSeen","strictProtectedRateWhenNotSeen","seenProtectedDelta","strictProtectedRateWhenPlayed","avgFirstActionRound")}})
        report["cardAnalytics"][v]=card_report

    expected=set(base); strict=(len(base)==2000)
    for v in variants:
        strict = strict and len(maps[v])==2000 and set(maps[v])==expected and len(tmaps[v])==2000 and set(tmaps[v])==expected
    report["strictValid"]=bool(strict)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2,sort_keys=True))
    csv_path=out.with_suffix(".cards.csv")
    with csv_path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(csv_rows[0].keys())); w.writeheader(); w.writerows(csv_rows)
    print(json.dumps({"strictValid":report["strictValid"],"variants":report["variants"],"paired":report["paired"],"telemetryCoverage":report["telemetryCoverage"]},indent=2,sort_keys=True))
    if not report["strictValid"]: raise SystemExit("STRICT_FOUR_ARCH_TELEMETRY_PAIRING_FAILED")

if __name__=="__main__": main()
