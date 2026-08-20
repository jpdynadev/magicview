#!/usr/bin/env python3
"""Architecture-aware sim-v2 worker.

Uses the architecture policy/decks while retaining sim-v2 cache identity,
exposure tracking, compact records, and session cleanup. Production workflows
must still request jvm-reuse=1 until the persistent equivalence gate clears.

Diagnostic runs can set SIM_V2_TRACE=1 or SIM_V2_CAPTURE_STDERR=1. In that
mode the wrapper preserves the Forge JVM stderr tail, the harness decoded-action
tail and the pilot prompt/answer tail directly in each compact result.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import sim_v2_worker_ultra as ultra


def _tail_text(path: str | Path | None, limit: int = 12000) -> str | None:
    if not path:
        return None
    try:
        text = Path(path).read_text(errors="replace")
    except Exception:
        return None
    return text[-limit:] if text else None


def _pilot_trace_tail(runner, result, limit: int = 12):
    try:
        suffix = f"{result.get('variant')}-{int(result.get('seed'))}-s{int(result.get('kinnanSeat'))}"
        path = runner.base.RESULT_DIR / f"pilot-trace-{suffix}.json"
        rows = json.loads(path.read_text())
        return rows[-limit:] if isinstance(rows, list) else None
    except Exception:
        return None


def _install_prompt_submission_guard(runner) -> None:
    original_rpc = runner.base.rpc
    current_prompt: dict[str, str] = {}
    submitted: set[tuple[str, str, str]] = set()
    stats = {"suppressed": 0}

    def guarded_rpc(proc, request):
        command = request.get("command")
        session = str(request.get("sessionId") or "")
        if command == "submitAction":
            prompt_id = current_prompt.get(session, "")
            payload = str(request.get("payload") or "")
            key = (session, prompt_id, payload)
            if prompt_id and key in submitted:
                stats["suppressed"] += 1
                return ""
            if prompt_id:
                submitted.add(key)
                try:
                    canonical = json.loads(payload)
                    if isinstance(canonical, dict):
                        canonical["__promptId"] = prompt_id
                        request = dict(request)
                        request["payload"] = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False)
                except Exception:
                    pass
            return original_rpc(proc, request)
        raw = original_rpc(proc, request)
        if command == "getPrompt" and raw:
            try:
                prompt = json.loads(raw)
                pid = str(prompt.get("promptId") or "")
                if pid:
                    previous = current_prompt.get(session)
                    if previous != pid:
                        current_prompt[session] = pid
                        kept = {k for k in submitted if k[0] != session or k[1] == pid}
                        submitted.clear(); submitted.update(kept)
            except Exception:
                pass
        return raw

    runner.base.rpc = guarded_rpc
    runner._V2_PROMPT_GUARD_STATS = stats


def _attach_prompt_guard_metric(runner) -> None:
    stats = getattr(runner, "_V2_PROMPT_GUARD_STATS", None)
    if not stats:
        return
    original_run = runner.run_game
    def guarded_run(*args, **kwargs):
        before = int(stats.get("suppressed", 0))
        result = original_run(*args, **kwargs)
        result["v2DuplicateSubmitsSuppressed"] = int(stats.get("suppressed", 0)) - before
        return result
    runner.run_game = guarded_run


def _install_forensic_stderr_capture(worker, runner) -> None:
    enabled = os.getenv("SIM_V2_CAPTURE_STDERR", "0") == "1" or os.getenv("SIM_V2_TRACE", "0") == "1"
    if not enabled:
        return
    pool_cls = worker.ForgeJvmPool
    original_init = pool_cls.__init__; original_spawn = pool_cls._spawn; original_close = pool_cls._close
    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs); self._forensic_stderr_path=None; self._forensic_stderr_handle=None; worker._ARCH_ACTIVE_POOL=self
    def patched_spawn(self, args, kwargs):
        old=getattr(self,"_forensic_stderr_handle",None)
        if old is not None:
            try: old.close()
            except Exception: pass
        handle=tempfile.NamedTemporaryFile(mode="w+",prefix="kinnan-forge-stderr-",suffix=".log",delete=False)
        old_devnull=subprocess.DEVNULL; subprocess.DEVNULL=handle
        try: proc=original_spawn(self,args,kwargs)
        finally: subprocess.DEVNULL=old_devnull
        self._forensic_stderr_handle=handle; self._forensic_stderr_path=handle.name
        return proc
    def stderr_tail(self,limit=12000): return _tail_text(getattr(self,"_forensic_stderr_path",None),limit)
    def patched_close(self):
        original_close(self); handle=getattr(self,"_forensic_stderr_handle",None)
        if handle is not None:
            try: handle.close()
            except Exception: pass
            self._forensic_stderr_handle=None
    pool_cls.__init__=patched_init; pool_cls._spawn=patched_spawn; pool_cls._close=patched_close; pool_cls.stderr_tail=stderr_tail
    original_run=runner.run_game
    def forensic_run_game(*args,**kwargs):
        result=original_run(*args,**kwargs); pool=getattr(worker,"_ARCH_ACTIVE_POOL",None)
        if pool is not None and hasattr(pool,"stderr_tail"): result["v2JvmStderrTail"]=pool.stderr_tail()
        result["v2HarnessActionTail"]=_tail_text(os.getenv("MANABREW_HARNESS_TRACE"),12000)
        result["v2PilotTraceTail"]=_pilot_trace_tail(runner,result)
        return result
    runner.run_game=forensic_run_game


def _install_semantic_prompt_ids(runner) -> None:
    original_run=runner.run_game
    def semantic_run_game(*args,**kwargs):
        original_rpc=runner.base.rpc; last_signature={}; semantic_advances=0
        def semantic_rpc(proc,request):
            nonlocal semantic_advances
            raw=original_rpc(proc,request)
            if request.get("command")!="getPrompt" or not raw: return raw
            try: prompt=json.loads(raw)
            except Exception: return raw
            original_id=prompt.get("promptId"); material={"decidingPlayerId":prompt.get("decidingPlayerId"),"input":prompt.get("input") or {}}
            encoded=json.dumps(material,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
            signature=hashlib.sha256(encoded).hexdigest()[:16]; key=(str(request.get("sessionId") or ""),str(original_id)); previous=last_signature.get(key)
            if previous is not None and previous!=signature: semantic_advances+=1
            last_signature[key]=signature; prompt["promptId"]=f"{original_id}:{signature}"
            return json.dumps(prompt,separators=(",",":"),ensure_ascii=False)
        runner.base.rpc=semantic_rpc
        try: result=original_run(*args,**kwargs)
        finally: runner.base.rpc=original_rpc
        result["v2SemanticPromptAdvances"]=semantic_advances
        return result
    runner.run_game=semantic_run_game


def main() -> int:
    os.environ.setdefault("SIM_V2_PROFILE", "arch-cold-v4-prompt-scoped")
    mode=ultra._arg_value("--mode","screen"); variant=ultra._arg_value("--variant","")
    if mode=="adversarial": import manabrew_pilot_arch_adv as config
    else: import manabrew_pilot_arch as config
    runner=config.runner
    if variant not in runner.VARIANT_FILES: raise SystemExit(f"unknown architecture variant {variant}; known={sorted(runner.VARIANT_FILES)}")
    runner._SIM_V2_HOTPATCH_META={"earlySuccess":False,"exactDeadline":False,"traceEnabled":True,"metricWrapperPreserved":True,"optimizedSource":None,"sessionLifecycle":"abort+reset","policy":"architecture-aware","semanticPromptIdentity":True,"promptConsumptionAck":True,"promptScopedActions":True,"duplicateSubmitGuard":True,"forensicStderrCapture":os.getenv("SIM_V2_CAPTURE_STDERR","0")=="1" or os.getenv("SIM_V2_TRACE","0")=="1"}
    requested_exposure=ultra._arg_values("--exposure-card"); deck_path=runner.base.DECK_DIR/runner.VARIANT_FILES[variant]
    observation_universe=sorted(set(ultra._deck_card_names(deck_path))|set(requested_exposure))
    _install_prompt_submission_guard(runner); _install_semantic_prompt_ids(runner); ultra._install_observation_tracker(runner,observation_universe); ultra._install_session_lifecycle(runner); _attach_prompt_guard_metric(runner)
    print("SIM_V2_ARCH_CONFIG "+json.dumps({**runner._SIM_V2_HOTPATCH_META,"variant":variant,"observationUniverse":len(observation_universe)},sort_keys=True),flush=True)
    import sim_v2_worker
    if mode=="adversarial": sys.modules["manabrew_pilot_precision_adv"]=config
    else: sys.modules["manabrew_pilot_precision"]=config
    _install_forensic_stderr_capture(sim_v2_worker,runner)
    original_compact=sim_v2_worker.compact_result
    def compact_with_events(result,cards):
        item=original_compact(result,cards); observed=set(result.get("v2ObservedCards") or []); observed.update(item.get("observedCards") or []); requested=set(cards); exposed=sorted(observed&requested); events=result.get("v2ObservationEvents") or []
        item["observedCards"]=sorted(observed); item["observedCardEvents"]=events; item["exposureCards"]=exposed; item["slotExposed"]=bool(exposed); item["exposureEvents"]=[event for event in events if event.get("card") in requested]
        item["podProfile"]=os.getenv("CEDH_POD","balanced") if mode=="adversarial" else "screen"
        item["v2EarlyExit"]=False; item["v2DeadlineExit"]=False; item["v2SessionCleanup"]=bool(result.get("v2SessionCleanup")); item["v2SessionCleanupError"]=result.get("v2SessionCleanupError"); item["v2SemanticPromptAdvances"]=int(result.get("v2SemanticPromptAdvances") or 0); item["v2DuplicateSubmitsSuppressed"]=int(result.get("v2DuplicateSubmitsSuppressed") or 0)
        if result.get("error"): item["error"]=result.get("error")
        if result.get("v2JvmStderrTail"): item["v2JvmStderrTail"]=result.get("v2JvmStderrTail")
        if result.get("v2HarnessActionTail"): item["v2HarnessActionTail"]=result.get("v2HarnessActionTail")
        if result.get("v2PilotTraceTail"): item["v2PilotTraceTail"]=result.get("v2PilotTraceTail")
        return item
    sim_v2_worker.compact_result=compact_with_events
    return sim_v2_worker.main()

if __name__=="__main__": raise SystemExit(main())
