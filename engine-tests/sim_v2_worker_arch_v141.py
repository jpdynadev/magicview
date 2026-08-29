#!/usr/bin/env python3
"""Architecture worker v1.41: production-safe cleanup for jvm-reuse=1.

The v1.40 Monolith repair gate completed all 38 semantic records, but 17/38
reported a cleanup exception from the post-abort `reset` RPC. Production Kinnan
workflows deliberately use --jvm-reuse 1, so the Forge JVM is discarded after
each game and a reset of that soon-to-be-closed process is both unnecessary and
an additional failure surface.

This wrapper changes cleanup only:
- abortGame remains mandatory for every observed session;
- with --jvm-reuse 1, successful abortGame is sufficient and the pool closes
  the JVM at the end of the one-game lease;
- with --jvm-reuse >1, retain abortGame + reset before a JVM can be reused;
- any required cleanup failure still marks cleanup false and kills the process.

No game decisions, endpoints, observation logic, or Forge legality/payment
semantics are changed.
"""
from __future__ import annotations

import sys
from typing import Any

import sim_v2_worker_ultra as ultra


def _install_session_lifecycle_v141(runner: Any) -> None:
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
        cleanup_mode = "abort_only_discard_jvm" if reuse_games == 1 else "abort_reset_reuse_jvm"

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

        if session_id and borrowed_proc is not None and borrowed_proc.poll() is None:
            try:
                original_rpc(borrowed_proc, {"command": "abortGame", "sessionId": session_id})
                if reuse_games > 1:
                    original_rpc(borrowed_proc, {"command": "reset"})
                cleanup_ok = True
            except Exception as exc:
                cleanup_error = repr(exc)
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
        result["v2SessionCleanupMode"] = cleanup_mode
        result["v2SessionJvmReuse"] = reuse_games
        return result

    runner.run_game = lifecycle_run_game


# sim_v2_worker_arch imports the ultra module and calls this hook at runtime.
# Replace only that hook before importing the architecture entrypoint.
ultra._install_session_lifecycle = _install_session_lifecycle_v141

import sim_v2_worker_arch as arch  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(arch.main())
