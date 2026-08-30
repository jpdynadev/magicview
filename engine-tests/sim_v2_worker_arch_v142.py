#!/usr/bin/env python3
"""Architecture worker v1.42: dispose the one-game JVM instead of RPC cleanup.

v1.41 proved that the recurring Java `replacement is null` exception is raised
by abortGame itself, not by the reset that v1.41 removed. Production Kinnan
workflows require --jvm-reuse 1, so no game session can ever be observed by a
subsequent simulation if the underlying Forge JVM is terminated after the game.

For jvm-reuse=1 this wrapper therefore performs no post-game harness RPC:
- capture the JVM/session created by startGame;
- let the pilot/Forge return the completed or horizon result unchanged;
- terminate and wait for the underlying one-game JVM;
- mark cleanup successful only after the process is confirmed stopped.

For jvm-reuse>1 the previous abortGame + reset contract is retained because the
process can actually service another game. No game decisions, endpoints,
observation logic, or Forge legality/payment semantics are changed.
"""
from __future__ import annotations

import sys
from typing import Any

import sim_v2_worker_ultra as ultra


def _stop_real_proc(borrowed_proc: Any) -> None:
    real_proc = getattr(borrowed_proc, "_proc", None)
    if real_proc is None:
        raise RuntimeError("missing_real_process")
    if real_proc.poll() is not None:
        return
    try:
        real_proc.terminate()
        real_proc.wait(timeout=5)
    except Exception:
        if real_proc.poll() is None:
            real_proc.kill()
            real_proc.wait(timeout=5)
    if real_proc.poll() is None:
        raise RuntimeError("jvm_process_still_alive_after_discard")


def _install_session_lifecycle_v142(runner: Any) -> None:
    original_run = runner.run_game
    original_rpc = runner.base.rpc
    try:
        reuse_games = max(1, int(ultra._arg_value("--jvm-reuse", "8")))
    except Exception:
        reuse_games = 8

    def lifecycle_run_game(*args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id: str | None = None
        borrowed_proc: Any = None
        cleanup_ok = False
        cleanup_error: str | None = None
        cleanup_mode = "discard_jvm_no_rpc" if reuse_games == 1 else "abort_reset_reuse_jvm"

        def tracking_rpc(proc: Any, request: dict[str, Any]):
            nonlocal session_id, borrowed_proc
            raw = original_rpc(proc, request)
            if request.get("command") == "startGame" and raw:
                import json
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

        try:
            if session_id is None or borrowed_proc is None:
                raise RuntimeError("no_session_observed")
            if reuse_games == 1:
                _stop_real_proc(borrowed_proc)
            else:
                if borrowed_proc.poll() is None:
                    original_rpc(borrowed_proc, {"command": "abortGame", "sessionId": session_id})
                    original_rpc(borrowed_proc, {"command": "reset"})
                else:
                    raise RuntimeError("reusable_jvm_exited_before_cleanup")
            cleanup_ok = True
        except Exception as exc:
            cleanup_error = repr(exc)
            try:
                if borrowed_proc is not None:
                    _stop_real_proc(borrowed_proc)
            except Exception:
                pass

        result["v2SessionCleanup"] = cleanup_ok
        result["v2SessionCleanupError"] = cleanup_error
        result["v2SessionCleanupMode"] = cleanup_mode
        result["v2SessionJvmReuse"] = reuse_games
        return result

    runner.run_game = lifecycle_run_game


ultra._install_session_lifecycle = _install_session_lifecycle_v142

import sim_v2_worker_arch as arch  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(arch.main())
