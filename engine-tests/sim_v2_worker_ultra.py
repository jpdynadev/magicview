#!/usr/bin/env python3
"""Persistent-JVM v2 entrypoint with reusable exposure instrumentation.

The trusted path deliberately preserves the validated pilot's trace semantics.
Earlier ultra profiles replaced the pilot trace with a sink; seeded equivalence
proved that transformation can change endpoint bookkeeping (seed 1720003 lost
its T4 firstAssemblyTurn). Persistent JVM reuse and observation tracking remain,
but semantic AST rewrites are disabled unless they are revalidated separately.

The cache records which cards from the Kinnan 99 were seen in Kinnan's live
zones or appeared in a small, concrete Forge choice pool. Broad library/tutor/
action payloads are intentionally excluded.

Persistent reuse follows Manabrew's own interactive-server lifecycle contract:
every completed/aborted game is removed with abortGame and the idle process is
reset before another session starts. If cleanup fails, the underlying JVM is
terminated so a dirty session can never contaminate the next seed.
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


def _prompt_choice_objects(prompt: dict[str, Any], max_pool: int = 16) -> list[Any]:
    """Return only constrained card-choice payloads.

    Manabrew can serialize a full library, broad tutor search, or action catalog
    inside a prompt. Counting those as exposure makes essentially the entire 99
    look observed. For conditional slot analysis we instead count cards that
    actually reach Kinnan's live zones and cards in small explicit selection
    pools such as Kinnan's top-five reveal.
    """
    inp = (prompt or {}).get("input") or {}
    out: list[Any] = []
    for key in (
        "cards", "candidates", "choices", "targets",
        "validCards", "availableCards", "selectableCards",
    ):
        value = inp.get(key)
        if isinstance(value, (list, tuple)):
            if 0 < len(value) <= max_pool:
                out.extend(value)
        elif isinstance(value, dict):
            if 0 < len(value) <= max_pool:
                out.append(value)
    return out


def _install_observation_tracker(runner: Any, tracked_cards: list[str]) -> None:
    cards = tuple(dict.fromkeys(tracked_cards))
    if not cards:
        return
    card_set = set(cards)
    prompt_matcher = re.compile("|".join(re.escape(card) for card in sorted(cards, key=len, reverse=True)))
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
                try:
                    prompt = json.loads(raw)
                except Exception:
                    prompt = {}
                for choice in _prompt_choice_objects(prompt):
                    text = json.dumps(choice, separators=(",", ":"), ensure_ascii=False)
                    for match in prompt_matcher.finditer(text):
                        mark(match.group(0), "prompt_small_choice")
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


def _install_session_lifecycle(runner: Any) -> None:
    """Close the interactive session and reset Forge between pooled games.

    The pinned harness only resets global counters automatically when its
    session map is empty. The legacy pilot normally exits the JVM after a game,
    so it never needed to call endGame/abortGame. A pooled JVM must do that
    explicitly. We track the session returned by startGame, abort it after the
    pilot returns (horizon exits are usually not natural game-over), then issue
    the harness reset command while idle. On any cleanup failure we terminate
    the real pooled JVM; the pool will respawn it on the next game.
    """
    original_run = runner.run_game
    original_rpc = runner.base.rpc

    def lifecycle_run_game(*args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id: str | None = None
        borrowed_proc: Any = None
        cleanup_ok = False
        cleanup_error: str | None = None

        def tracking_rpc(proc: Any, request: dict[str, Any]):
            nonlocal session_id, borrowed_proc
            raw = original_rpc(proc, request)
            if request.get("command") == "startGame" and raw:
                try:
                    payload = json.loads(raw)
                    sid = payload.get("sessionId")
                    if sid:
                        session_id = str(sid)
                        borrowed_proc = proc
                except Exception:
                    pass
            return raw

        runner.base.rpc = tracking_rpc
        result: dict[str, Any]
        try:
            result = original_run(*args, **kwargs)
        finally:
            runner.base.rpc = original_rpc

        if session_id and borrowed_proc is not None and borrowed_proc.poll() is None:
            try:
                original_rpc(borrowed_proc, {"command": "abortGame", "sessionId": session_id})
                original_rpc(borrowed_proc, {"command": "reset"})
                cleanup_ok = True
            except Exception as exc:
                cleanup_error = repr(exc)
                # _BorrowedProc exposes the real process as _proc. Killing it is
                # safer than allowing a dirty session to affect another seed.
                real_proc = getattr(borrowed_proc, "_proc", None)
                try:
                    if real_proc is not None:
                        real_proc.terminate()
                        real_proc.wait(timeout=3)
                except Exception:
                    try:
                        if real_proc is not None:
                            real_proc.kill()
                    except Exception:
                        pass
        elif session_id is None:
            cleanup_error = "no_session_observed"

        result["v2SessionCleanup"] = cleanup_ok
        result["v2SessionCleanupError"] = cleanup_error
        return result

    runner.run_game = lifecycle_run_game


def main() -> int:
    # ultra-v7 adds the missing interactive-session lifecycle required for safe
    # JVM reuse. Optimizer fingerprinting also invalidates v6 rows.
    os.environ.setdefault("SIM_V2_PROFILE", "ultra-v7")

    mode = _arg_value("--mode", "screen")
    variant = _arg_value("--variant", "")
    if mode == "adversarial":
        import manabrew_pilot_precision_adv as config
    else:
        import manabrew_pilot_precision as config

    if variant not in config.runner.VARIANT_FILES:
        raise SystemExit(f"unknown variant {variant}; known={sorted(config.runner.VARIANT_FILES)}")

    # No semantic AST hotpatch is installed on the trusted path. The only
    # execution optimization is Forge JVM reuse in sim_v2_worker.ForgeJvmPool.
    config.runner._SIM_V2_HOTPATCH_META = {
        "earlySuccess": False,
        "exactDeadline": False,
        "traceEnabled": True,
        "traceInitializersReplaced": 0,
        "earlyExitSitesInserted": 0,
        "deadlineExitSitesInserted": 0,
        "metricWrapperPreserved": True,
        "optimizedSource": None,
        "sessionLifecycle": "abort+reset",
    }

    requested_exposure = _arg_values("--exposure-card")
    deck_path = config.runner.base.DECK_DIR / config.runner.VARIANT_FILES[variant]
    observation_universe = sorted(set(_deck_card_names(deck_path)) | set(requested_exposure))
    _install_observation_tracker(config.runner, observation_universe)
    _install_session_lifecycle(config.runner)
    print(
        "SIM_V2_HOTPATCH "
        + json.dumps({**config.runner._SIM_V2_HOTPATCH_META, "observationUniverse": len(observation_universe)}, sort_keys=True),
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
        item["v2EarlyExit"] = False
        item["v2DeadlineExit"] = False
        item["v2SessionCleanup"] = bool(result.get("v2SessionCleanup"))
        item["v2SessionCleanupError"] = result.get("v2SessionCleanupError")
        return item

    sim_v2_worker.compact_result = compact_with_events
    return sim_v2_worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
