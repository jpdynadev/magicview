#!/usr/bin/env python3
"""v1.42 lifecycle worker with read-only full-card telemetry sidecars."""
from __future__ import annotations
import json, os
from pathlib import Path
import sim_v2_worker_arch_v142  # installs discard-JVM lifecycle
import sim_v2_worker_arch as arch

def strict_pt4(r):
    turn=r.get("firstAttemptTurn")
    certified=bool(r.get("certifiedDeterministicAttempt") or (r.get("deterministicT4") and turn is not None and int(turn)<=4))
    return bool(r.get("protectedAttempt")) and certified and turn is not None and int(turn)<=4

def main():
    mode=arch.ultra._arg_value("--mode","screen")
    if mode=="adversarial":
        import manabrew_pilot_arch_adv as config
    else:
        import manabrew_pilot_arch as config
    from card_telemetry_v1 import install
    install(config.runner)
    outdir=Path(os.getenv("CARD_TELEMETRY_DIR","out/card-telemetry")); outdir.mkdir(parents=True,exist_ok=True)
    original=config.runner.run_game
    def sidecar(*args,**kwargs):
        result=original(*args,**kwargs)
        telemetry=result.get("cardTelemetry") or {}
        if telemetry:
            variant=str(result.get("variant") or arch.ultra._arg_value("--variant","unknown"))
            seed=int(result.get("seed") or 0); seat=int(result.get("kinnanSeat") or 0)
            pod=os.getenv("CEDH_POD","balanced") if mode=="adversarial" else "screen"
            payload={
              "schema":"kinnan-card-telemetry-v2-source","pilotVersion":result.get("pilotVersion"),
              "variant":variant,"variantDeckSha256":result.get("variantDeckSha256"),"seed":seed,
              "kinnanSeat":seat,"podProfile":pod,"status":result.get("status"),
              "kinnanWon":bool(result.get("kinnanWon")),"winnerSeat":result.get("winnerSeat"),
              "firstAssemblyTurn":result.get("firstAssemblyTurn"),"firstAttemptTurn":result.get("firstAttemptTurn"),
              "certifiedDeterministicAttempt":bool(result.get("certifiedDeterministicAttempt")),
              "protectedAttempt":bool(result.get("protectedAttempt")),"strictProtectedT4":strict_pt4(result),
              "attemptResolved":bool(result.get("attemptResolved")),"comboLine":result.get("comboLine"),
              "primaryFailureCode":result.get("primaryFailureCode"),"mulligans":(result.get("mulligans") or {}).get(str(seat)),
              "protectionAvailable":result.get("protectionAvailable") or [],"telemetry":telemetry,
              "rawActionTrace":telemetry.get("events") or []
            }
            (outdir/f"{variant}-s{seat}-seed{seed}-{pod}.json").write_text(json.dumps(payload,separators=(",",":"),ensure_ascii=False))
        return result
    config.runner.run_game=sidecar
    return arch.main()

if __name__=="__main__":
    raise SystemExit(main())
