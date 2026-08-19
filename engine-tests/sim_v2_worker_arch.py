#!/usr/bin/env python3
"""Architecture-aware sim-v2 worker.

Uses the architecture policy/decks while retaining sim-v2 cache identity,
exposure tracking, compact records, and session cleanup. Production workflows
must still request jvm-reuse=1 until the persistent equivalence gate clears.

Diagnostic runs can set SIM_V2_TRACE=1 or SIM_V2_CAPTURE_STDERR=1. In that
mode the wrapper preserves the Forge JVM stderr tail, the harness decoded-action
tail and the pilot prompt/answer tail directly in each compact result. This is
important because sim_v2_worker normally redirects pooled JVM stderr to DEVNULL.
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


def _install_forensic_stderr_capture(worker, runner) -> None:
    """Capture stderr without changing trusted game semantics.

    ForgeJvmPool normally replaces the pilot's stderr=PIPE with DEVNULL. That
    made game-thread RuntimeExceptions invisible and caused stale_prompt_timeout
    to be a diagnostic dead end. In forensic mode we redirect each pooled JVM's
    stderr to a temporary file instead, keep the pilot-facing BorrowedProc
    semantics unchanged, and copy only the tail into the result after the game.
    """
    enabled = os.getenv("SIM_V2_CAPTURE_STDERR", "0") == "1" or os.getenv("SIM_V2_TRACE", "0") == "1"
    if not enabled:
        return

    pool_cls = worker.ForgeJvmPool
    original_init = pool_cls.__init__
    original_spawn = pool_cls._spawn
    original_close = pool_cls._close

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._forensic_stderr_path = None
        self._forensic_stderr_handle = None
        worker._ARCH_ACTIVE_POOL = self

    def patched_spawn(self, args, kwargs):
        old_handle = getattr(self, "_forensic_stderr_handle", None)
        if old_handle is not None:
            try:
                old_handle.close()
            except Exception:
                pass
        handle = tempfile.NamedTemporaryFile(
            mode="w+", prefix="kinnan-forge-stderr-", suffix=".log", delete=False
        )
        old_devnull = subprocess.DEVNULL
        subprocess.DEVNULL = handle
        try:
            proc = original_spawn(self, args, kwargs)
        finally:
            subprocess.DEVNULL = old_devnull
        self._forensic_stderr_handle = handle
        self._forensic_stderr_path = handle.name
        return proc

    def stderr_tail(self, limit=12000):
        return _tail_text(getattr(self, "_forensic_stderr_path", None), limit)

    def patched_close(self):
        original_close(self)
        handle = getattr(self, "_forensic_stderr_handle", None)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
            self._forensic_stderr_handle = None

    pool_cls.__init__ = patched_init
    pool_cls._spawn = patched_spawn
    pool_cls._close = patched_close
    pool_cls.stderr_tail = stderr_tail

    original_run = runner.run_game

    def forensic_run_game(*args, **kwargs):
        result = original_run(*args, **kwargs)
        pool = getattr(worker, "_ARCH_ACTIVE_POOL", None)
        if pool is not None and hasattr(pool, "stderr_tail"):
            result["v2JvmStderrTail"] = pool.stderr_tail()
        result["v2HarnessActionTail"] = _tail_text(os.getenv("MANABREW_HARNESS_TRACE"), 12000)
        result["v2PilotTraceTail"] = _pilot_trace_tail(runner, result)
        return result

    runner.run_game = forensic_run_game


def _install_semantic_prompt_ids(runner) -> None:
    """Retain the prior semantic-prompt probe for comparability.

    The 96-game validation proved this mechanism does not explain the stale
    failures (zero semantic advances), but leaving the no-op probe in place keeps
    pre/post forensic records directly comparable until the actual root cause is
    repaired.
    """
    original_run = runner.run_game

    def semantic_run_game(*args, **kwargs):
        original_rpc = runner.base.rpc
        last_signature: dict[tuple[str, str], str] = {}
        semantic_advances = 0

        def semantic_rpc(proc, request):
            nonlocal semantic_advances
            raw = original_rpc(proc, request)
            if request.get("command") != "getPrompt" or not raw:
                return raw
            try:
                prompt = json.loads(raw)
            except Exception:
                return raw

            original_id = prompt.get("promptId")
            material = {
                "decidingPlayerId": prompt.get("decidingPlayerId"),
                "input": prompt.get("input") or {},
            }
            encoded = json.dumps(
                material,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            signature = hashlib.sha256(encoded).hexdigest()[:16]
            key = (str(request.get("sessionId") or ""), str(original_id))
            previous = last_signature.get(key)
            if previous is not None and previous != signature:
                semantic_advances += 1
            last_signature[key] = signature
            prompt["promptId"] = f"{original_id}:{signature}"
            return json.dumps(prompt, separators=(",", ":"), ensure_ascii=False)

        runner.base.rpc = semantic_rpc
        try:
            result = original_run(*args, **kwargs)
        finally:
            runner.base.rpc = original_rpc
        result["v2SemanticPromptAdvances"] = semantic_advances
        return result

    runner.run_game = semantic_run_game


def main() -> int:
    os.environ.setdefault("SIM_V2_PROFILE", "arch-cold-v2-semantic-prompt")
    mode = ultra._arg_value("--mode", "screen")
    variant = ultra._arg_value("--variant", "")

    if mode == "adversarial":
        import manabrew_pilot_arch_adv as config
    else:
        import manabrew_pilot_arch as config

    runner = config.runner
    if variant not in runner.VARIANT_FILES:
        raise SystemExit(f"unknown architecture variant {variant}; known={sorted(runner.VARIANT_FILES)}")

    runner._SIM_V2_HOTPATCH_META = {
        "earlySuccess": False,
        "exactDeadline": False,
        "traceEnabled": True,
        "metricWrapperPreserved": True,
        "optimizedSource": None,
        "sessionLifecycle": "abort+reset",
        "policy": "architecture-aware",
        "semanticPromptIdentity": True,
        "forensicStderrCapture": os.getenv("SIM_V2_CAPTURE_STDERR", "0") == "1" or os.getenv("SIM_V2_TRACE", "0") == "1",
    }

    requested_exposure = ultra._arg_values("--exposure-card")
    deck_path = runner.base.DECK_DIR / runner.VARIANT_FILES[variant]
    observation_universe = sorted(set(ultra._deck_card_names(deck_path)) | set(requested_exposure))
    _install_semantic_prompt_ids(runner)
    ultra._install_observation_tracker(runner, observation_universe)
    ultra._install_session_lifecycle(runner)
    print(
        "SIM_V2_ARCH_CONFIG "
        + json.dumps({**runner._SIM_V2_HOTPATCH_META, "variant": variant, "observationUniverse": len(observation_universe)}, sort_keys=True),
        flush=True,
    )

    import sim_v2_worker

    # sim_v2_worker.main() normally imports the precision configuration. Alias
    # the already-loaded architecture config so the exact configured runner is
    # preserved.
    if mode == "adversarial":
        sys.modules["manabrew_pilot_precision_adv"] = config
    else:
        sys.modules["manabrew_pilot_precision"] = config

    _install_forensic_stderr_capture(sim_v2_worker, runner)

    original_compact = sim_v2_worker.compact_result

    def compact_with_events(result, cards):
        item = original_compact(result, cards)
        observed = set(result.get("v2ObservedCards") or [])
        observed.update(item.get("observedCards") or [])
        requested = set(cards)
        exposed = sorted(observed & requested)
        events = result.get("v2ObservationEvents") or []
        item["observedCards"] = sorted(observed)
        item["observedCardEvents"] = events
        item["exposureCards"] = exposed
        item["slotExposed"] = bool(exposed)
        item["exposureEvents"] = [event for event in events if event.get("card") in requested]
        item["v2EarlyExit"] = False
        item["v2DeadlineExit"] = False
        item["v2SessionCleanup"] = bool(result.get("v2SessionCleanup"))
        item["v2SessionCleanupError"] = result.get("v2SessionCleanupError")
        item["v2SemanticPromptAdvances"] = int(result.get("v2SemanticPromptAdvances") or 0)
        if result.get("v2JvmStderrTail"):
            item["v2JvmStderrTail"] = result.get("v2JvmStderrTail")
        if result.get("v2HarnessActionTail"):
            item["v2HarnessActionTail"] = result.get("v2HarnessActionTail")
        if result.get("v2PilotTraceTail"):
            item["v2PilotTraceTail"] = result.get("v2PilotTraceTail")
        return item

    sim_v2_worker.compact_result = compact_with_events
    return sim_v2_worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
