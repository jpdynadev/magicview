#!/usr/bin/env python3
"""Ultra entrypoint: validated v2 worker plus pilot hot-path optimizations.

Adds lightweight generic card-observation instrumentation without retaining the
full prompt trace. The cache records which cards from the Kinnan 99 were seen in
Kinnan's live zones or appeared in Forge prompts/selections. A later experiment
can therefore relabel exposure for a new singleton/package from cached games
without rerunning Forge.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _arg_value(flag: str, default: str) -> str:
    try:
        i = sys.argv.index(flag)
        return sys.argv[i + 1]
    except (ValueError, IndexError):
        return default


def _arg_values(flag: str) -> list[str]:
    out: list[str] = []
    for i, token in enumerate(sys.argv[:-1]):
        if token == flag:
            out.append(sys.argv[i + 1])
    return out


def _deck_card_names(path: Path) -> list[str]:
    names: list[str] = []
    active = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("["):
            active = line in {"[Commander]", "[Main]"}
            continue
        if not active or not line:
            continue
        m = re.match(r"^\d+\s+(.+?)\s*$", line)
        if m:
            names.append(m.group(1))
    return names


def _install_observation_tracker(runner: Any, tracked_cards: list[str]) -> None:
    cards = tuple(dict.fromkeys(tracked_cards))
    if not cards:
        return
    card_set = set(cards)
    original_run = runner.run_game

    def tracked_run_game(*args: Any, **kwargs: Any) -> dict[str, Any]:
        kinnan_seat = int(args[4] if len(args) > 4 else kwargs.get("kinnan_seat", 0))
        events: dict[tuple[str, str], int] = {}
        original_zone_cards = runner.base.zone_cards
        original_rpc = runner.base.rpc

        def mark(card: str, reason: str) -> None:
            events[(card, reason)] = events.get((card, reason), 0) + 1

        def zone_cards(snapshot: dict[str, Any], player: int, zone: str):
            result = original_zone_cards(snapshot, player, zone)
            if player == kinnan_seat and zone in {"hand", "battlefield", "graveyard", "exile", "command"}:
                for obj in result or []:
                    name = runner.base.card_name(obj)
                    if name in card_set:
                        mark(name, f"zone:{zone}")
            return result

        def rpc(proc: Any, request: dict[str, Any]):
            raw = original_rpc(proc, request)
            if request.get("command") == "getPrompt" and raw:
                text = str(raw)
                for card in cards:
                    if card in text:
                        mark(card, "prompt")
            return raw

        runner.base.zone_cards = zone_cards
        runner.base.rpc = rpc
        try:
            result = original_run(*args, **kwargs)
        finally:
            runner.base.zone_cards = original_zone_cards
            runner.base.rpc = original_rpc
        result["v2ObservationEvents"] = [
            {"card": card, "reason": reason, "count": count}
            for (card, reason), count in sorted(events.items())
        ]
        result["v2ObservedCards"] = sorted({card for card, _ in events})
        return result

    runner.run_game = tracked_run_game


def main() -> int:
    # Distinguish early-stopping/instrumented results from the compatibility
    # worker even when the underlying pilot/deck/seed are identical.
    os.environ.setdefault("SIM_V2_PROFILE", "ultra-v2")

    mode = _arg_value("--mode", "screen")
    variant = _arg_value("--variant", "")
    if mode == "adversarial":
        import manabrew_pilot_precision_adv as config
    else:
        import manabrew_pilot_precision as config

    if variant not in config.runner.VARIANT_FILES:
        raise SystemExit(f"unknown variant {variant}; known={sorted(config.runner.VARIANT_FILES)}")

    from sim_v2_hotpatch import install

    trace_enabled = os.getenv("SIM_V2_TRACE", "0").lower() in {"1", "true", "yes"}
    early_success = os.getenv("SIM_V2_EARLY_SUCCESS", "1").lower() not in {"0", "false", "no"}
    exact_deadline = os.getenv("SIM_V2_EXACT_DEADLINE", "1").lower() not in {"0", "false", "no"}
    meta = install(
        config.runner,
        early_success=early_success,
        trace_enabled=trace_enabled,
        exact_deadline=exact_deadline,
    )

    requested_exposure = _arg_values("--exposure-card")
    deck_path = config.runner.base.DECK_DIR / config.runner.VARIANT_FILES[variant]
    observation_universe = sorted(set(_deck_card_names(deck_path)) | set(requested_exposure))
    _install_observation_tracker(config.runner, observation_universe)
    print(
        "SIM_V2_HOTPATCH "
        + json.dumps({**meta, "observationUniverse": len(observation_universe)}, sort_keys=True),
        flush=True,
    )

    import sim_v2_worker

    original_compact = sim_v2_worker.compact_result

    def compact_with_events(result: dict[str, Any], cards: list[str]) -> dict[str, Any]:
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
        item["exposureEvents"] = [e for e in events if e.get("card") in requested]
        item["v2EarlyExit"] = bool(result.get("v2EarlyExit"))
        item["v2DeadlineExit"] = bool(result.get("v2DeadlineExit"))
        return item

    sim_v2_worker.compact_result = compact_with_events
    return sim_v2_worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
