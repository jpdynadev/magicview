#!/usr/bin/env python3
"""Forensic-only entry point for architecture simulations.

This leaves the production sim-v2 path unchanged. It replaces only the
forensic stderr capture hook so diagnostics survive when runner.run_game()
raises before a compact result can be decorated.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import sim_v2_worker_arch as arch


def _write_diag(payload: dict) -> None:
    out_dir = Path(os.getenv("SIM_V2_FORENSIC_DIR", "out"))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "forensic-crash-diagnostics.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _install_forensic_stderr_capture(worker, runner) -> None:
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
        old = getattr(self, "_forensic_stderr_handle", None)
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        out_dir = Path(os.getenv("SIM_V2_FORENSIC_DIR", "out"))
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"forge-stderr-start{int(getattr(self, 'starts', 0)) + 1}.log"
        handle = path.open("w+")
        # sim_v2_worker.ForgeJvmPool._spawn hardcodes subprocess.DEVNULL.
        # Temporarily point that sentinel at our real file handle so the exact
        # production spawn code is retained while stderr becomes inspectable.
        old_devnull = subprocess.DEVNULL
        subprocess.DEVNULL = handle
        try:
            proc = original_spawn(self, args, kwargs)
        finally:
            subprocess.DEVNULL = old_devnull
        self._forensic_stderr_handle = handle
        self._forensic_stderr_path = str(path)
        return proc

    def stderr_tail(self, limit=20000):
        return arch._tail_text(getattr(self, "_forensic_stderr_path", None), limit)

    def patched_close(self):
        original_close(self)
        handle = getattr(self, "_forensic_stderr_handle", None)
        if handle is not None:
            try:
                handle.flush()
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
        try:
            result = original_run(*args, **kwargs)
        except Exception as exc:
            pool = getattr(worker, "_ARCH_ACTIVE_POOL", None)
            proc = getattr(pool, "proc", None) if pool is not None else None
            return_code = None
            if proc is not None:
                try:
                    return_code = proc.poll()
                except Exception:
                    pass
            stderr_tail = pool.stderr_tail() if pool is not None and hasattr(pool, "stderr_tail") else None
            diag = {
                "exception": repr(exc),
                "jvmReturnCode": return_code,
                "jvmAliveAtException": return_code is None if proc is not None else None,
                "stderrPath": getattr(pool, "_forensic_stderr_path", None) if pool is not None else None,
                "jvmStderrTail": stderr_tail,
                "harnessActionTail": arch._tail_text(os.getenv("MANABREW_HARNESS_TRACE"), 20000),
                "runArgs": [str(x) for x in args],
                "runKwargs": {k: str(v) for k, v in kwargs.items()},
            }
            _write_diag(diag)
            # Keep a global copy so compact_result can include it if desired,
            # while preserving the existing worker's crash classification.
            worker._ARCH_LAST_FORENSIC_DIAG = diag
            raise

        pool = getattr(worker, "_ARCH_ACTIVE_POOL", None)
        if pool is not None and hasattr(pool, "stderr_tail"):
            result["v2JvmStderrTail"] = pool.stderr_tail()
            proc = getattr(pool, "proc", None)
            if proc is not None:
                try:
                    result["v2JvmReturnCode"] = proc.poll()
                except Exception:
                    pass
        result["v2HarnessActionTail"] = arch._tail_text(os.getenv("MANABREW_HARNESS_TRACE"), 20000)
        result["v2PilotTraceTail"] = arch._pilot_trace_tail(runner, result)
        return result

    runner.run_game = forensic_run_game


arch._install_forensic_stderr_capture = _install_forensic_stderr_capture

if __name__ == "__main__":
    raise SystemExit(arch.main())
