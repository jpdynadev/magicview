#!/usr/bin/env python3
"""Harden sim-v2 session cleanup after a terminal game result.

Some Forge states can throw while handling abortGame/reset even after the game
has already reached a valid terminal/horizon result.  The existing lifecycle
wrapper correctly terminates the real pooled JVM on that exception, preventing
cross-game contamination, but still reports cleanup=false.  This patch records
successful hard termination as an isolation-safe cleanup while preserving the
original RPC exception for diagnostics.  A failed hard termination remains a
true cleanup failure.
"""
from pathlib import Path

ultra = Path('engine-tests/sim_v2_worker_ultra.py')
text = ultra.read_text()
old = '''        cleanup_ok = False\n        cleanup_error: str | None = None\n'''
new = '''        cleanup_ok = False\n        cleanup_error: str | None = None\n        cleanup_mode: str | None = None\n        cleanup_isolated = False\n'''
if old not in text:
    raise SystemExit('ultra lifecycle state anchor not found')
text = text.replace(old, new, 1)

old = '''                original_rpc(borrowed_proc, {"command": "abortGame", "sessionId": session_id})\n                original_rpc(borrowed_proc, {"command": "reset"})\n                cleanup_ok = True\n            except Exception as exc:\n                cleanup_error = repr(exc)\n                # _BorrowedProc exposes the real process as _proc. Killing it is\n                # safer than allowing a dirty session to affect another seed.\n                real_proc = getattr(borrowed_proc, "_proc", None)\n                try:\n                    if real_proc is not None:\n                        real_proc.terminate()\n                        real_proc.wait(timeout=3)\n                except Exception:\n                    try:\n                        if real_proc is not None:\n                            real_proc.kill()\n                    except Exception:\n                        pass\n        elif session_id is None:\n            cleanup_error = "no_session_observed"\n\n        result["v2SessionCleanup"] = cleanup_ok\n        result["v2SessionCleanupError"] = cleanup_error\n'''
new = '''                original_rpc(borrowed_proc, {"command": "abortGame", "sessionId": session_id})\n                original_rpc(borrowed_proc, {"command": "reset"})\n                cleanup_ok = True\n                cleanup_isolated = True\n                cleanup_mode = "abort+reset"\n            except Exception as exc:\n                cleanup_error = repr(exc)\n                # _BorrowedProc exposes the real process as _proc.  If normal\n                # cleanup itself trips a Forge bug, destroying that exact JVM is\n                # still a complete isolation boundary: no session from this game\n                # can contaminate the next seed.  Preserve the RPC error, but\n                # distinguish isolation success from an unresolved cleanup fault.\n                real_proc = getattr(borrowed_proc, "_proc", None)\n                hard_stopped = False\n                if real_proc is not None:\n                    try:\n                        real_proc.terminate()\n                        real_proc.wait(timeout=3)\n                        hard_stopped = real_proc.poll() is not None\n                    except Exception:\n                        try:\n                            real_proc.kill()\n                            real_proc.wait(timeout=3)\n                            hard_stopped = real_proc.poll() is not None\n                        except Exception:\n                            hard_stopped = False\n                if hard_stopped:\n                    cleanup_ok = True\n                    cleanup_isolated = True\n                    cleanup_mode = "hard-stop-after-cleanup-error"\n                else:\n                    cleanup_mode = "cleanup-error-unisolated"\n        elif session_id is None:\n            cleanup_error = "no_session_observed"\n            cleanup_mode = "no-session-observed"\n\n        result["v2SessionCleanup"] = cleanup_ok\n        result["v2SessionCleanupIsolated"] = cleanup_isolated\n        result["v2SessionCleanupMode"] = cleanup_mode\n        result["v2SessionCleanupError"] = cleanup_error\n'''
if old not in text:
    raise SystemExit('ultra cleanup implementation anchor not found')
text = text.replace(old, new, 1)

old = '''        item["v2SessionCleanup"] = bool(result.get("v2SessionCleanup"))\n        item["v2SessionCleanupError"] = result.get("v2SessionCleanupError")\n'''
new = '''        item["v2SessionCleanup"] = bool(result.get("v2SessionCleanup"))\n        item["v2SessionCleanupIsolated"] = bool(result.get("v2SessionCleanupIsolated"))\n        item["v2SessionCleanupMode"] = result.get("v2SessionCleanupMode")\n        item["v2SessionCleanupError"] = result.get("v2SessionCleanupError")\n'''
if old not in text:
    raise SystemExit('ultra compact cleanup anchor not found')
text = text.replace(old, new, 1)
ultra.write_text(text)

arch = Path('engine-tests/sim_v2_worker_arch.py')
a = arch.read_text()
old = '''        item["v2EarlyExit"]=False; item["v2DeadlineExit"]=False; item["v2SessionCleanup"]=bool(result.get("v2SessionCleanup")); item["v2SessionCleanupError"]=result.get("v2SessionCleanupError"); item["v2SemanticPromptAdvances"]=int(result.get("v2SemanticPromptAdvances") or 0); item["v2DuplicateSubmitsSuppressed"]=int(result.get("v2DuplicateSubmitsSuppressed") or 0)\n'''
new = '''        item["v2EarlyExit"]=False; item["v2DeadlineExit"]=False; item["v2SessionCleanup"]=bool(result.get("v2SessionCleanup")); item["v2SessionCleanupIsolated"]=bool(result.get("v2SessionCleanupIsolated")); item["v2SessionCleanupMode"]=result.get("v2SessionCleanupMode"); item["v2SessionCleanupError"]=result.get("v2SessionCleanupError"); item["v2SemanticPromptAdvances"]=int(result.get("v2SemanticPromptAdvances") or 0); item["v2DuplicateSubmitsSuppressed"]=int(result.get("v2DuplicateSubmitsSuppressed") or 0)\n'''
if old not in a:
    raise SystemExit('arch compact cleanup anchor not found')
a = a.replace(old, new, 1)
arch.write_text(a)
print('applied sim-v2 hard-stop cleanup isolation fix')
