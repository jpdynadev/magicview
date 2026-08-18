#!/usr/bin/env python3
"""Architecture-aware sim-v2 worker.

Uses the architecture policy/decks while retaining sim-v2 cache identity,
exposure tracking, compact records, and session cleanup. Production workflows
must still request jvm-reuse=1 until the persistent equivalence gate clears.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import sim_v2_worker_ultra as ultra


def _install_semantic_prompt_ids(runner) -> None:
    """Treat changed prompt payloads as progress even when promptId is reused.

    Manabrew may keep one promptId while mutating that prompt's input during a
    multi-step decision/payment. The v8 pilot historically used promptId alone
    to detect a repeated prompt, so a changed action/selection payload could be
    ignored for 60 seconds and reported as stale_prompt_timeout.

    Give the pilot an internal prompt identity composed of Forge's promptId plus
    a stable hash of the deciding player and input payload. Truly identical
    prompts remain identical (so existing retry/stall handling still applies),
    while a semantic change is processed immediately as new progress. The
    transformed ID is pilot-local; submitAction does not send promptId back to
    Manabrew, so Forge protocol semantics are unchanged.
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

    # sim_v2_worker.main() normally imports the precision screen/adversarial
    # configuration internally.  That is correct for precision experiments but
    # would silently replace the architecture runner/pilot identity after this
    # wrapper has installed architecture-aware card semantics and observation
    # instrumentation.  Alias the already-loaded architecture config under the
    # names main() imports so the exact configured runner is preserved.
    if mode == "adversarial":
        sys.modules["manabrew_pilot_precision_adv"] = config
    else:
        sys.modules["manabrew_pilot_precision"] = config

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
        return item

    sim_v2_worker.compact_result = compact_with_events
    return sim_v2_worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
