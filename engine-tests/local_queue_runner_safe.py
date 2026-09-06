#!/usr/bin/env python3
"""Safety/health wrapper for the canonical local Kinnan queue worker.

This wrapper never implements simulation semantics. It gates queue access before
``local_queue_runner.main`` can claim a shard, then publishes a lightweight
runner heartbeat while the canonical worker owns execution. Both local machines
and the GitHub fallback invoke this same wrapper.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import local_queue_runner as worker

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "kinnan_policy_parity_manifest_v2.json"
HEARTBEAT_SECONDS = 60


def _manifest() -> tuple[dict[str, Any], str]:
    raw = MANIFEST_PATH.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _has_flag(argv: list[str], flag: str) -> bool:
    return flag in argv


def _runner_id(argv: list[str]) -> tuple[list[str], str]:
    if "--runner-id" in argv:
        index = argv.index("--runner-id")
        if index + 1 >= len(argv) or not argv[index + 1].strip():
            raise SystemExit("--runner-id requires a non-empty value")
        return argv, argv[index + 1]
    value = f"{socket.gethostname()}-{os.getpid()}"
    return [*argv, "--runner-id", value], value


def _runner_kind() -> str:
    value = os.environ.get("KINNAN_RUNNER_KIND", "local").strip().lower()
    if value not in {"local", "github"}:
        raise SystemExit("KINNAN_RUNNER_KIND must be 'local' or 'github'")
    return value


def _repo_sha() -> str:
    return (
        os.environ.get("KINNAN_REPO_SHA")
        or os.environ.get("GITHUB_SHA")
        or "unknown"
    )


def _touch(
    api: worker.NeonDataApi,
    *,
    runner_id: str,
    runner_kind: str,
    status: str,
    manifest_sha256: str,
    ranking_ready: bool,
) -> None:
    value = api.rpc("touch_sim_runner_heartbeat", {
        "p_runner_id": runner_id,
        "p_runner_kind": runner_kind,
        "p_status": status,
        "p_repo_sha": _repo_sha(),
        "p_engine_id": os.environ.get("MANABREW_REF", ""),
        "p_manifest_sha256": manifest_sha256,
        "p_ranking_ready": ranking_ready,
        "p_current_shard": None,
    })
    if not worker._rpc_boolean(value):
        raise worker.QueueError("runner heartbeat update was rejected")


class RunnerHeartbeat:
    def __init__(
        self,
        api: worker.NeonDataApi,
        *,
        runner_id: str,
        runner_kind: str,
        manifest_sha256: str,
        ranking_ready: bool,
    ) -> None:
        self.api = api
        self.runner_id = runner_id
        self.runner_kind = runner_kind
        self.manifest_sha256 = manifest_sha256
        self.ranking_ready = ranking_ready
        self.stop_event = threading.Event()
        self.error: Exception | None = None
        self.thread = threading.Thread(target=self._loop, name=f"runner-health-{runner_id}", daemon=True)

    def _send(self, status: str) -> None:
        _touch(
            self.api,
            runner_id=self.runner_id,
            runner_kind=self.runner_kind,
            status=status,
            manifest_sha256=self.manifest_sha256,
            ranking_ready=self.ranking_ready,
        )

    def _loop(self) -> None:
        while not self.stop_event.wait(HEARTBEAT_SECONDS):
            try:
                self._send("active")
            except Exception as exc:  # health loss should make fallback eligible
                self.error = exc
                return

    def __enter__(self) -> "RunnerHeartbeat":
        self._send("active")
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)
        final_status = "error" if exc_type is not None or self.error is not None else "idle"
        try:
            self._send(final_status)
        except Exception:
            pass


def main() -> int:
    manifest, manifest_sha256 = _manifest()
    ranking_ready = bool(manifest.get("rankingReady"))
    original_argv = list(sys.argv[1:])

    # Dry-run intentionally delegates to the canonical worker so operators can
    # exercise semantic/component preflight without making database calls.
    if _has_flag(original_argv, "--dry-run"):
        return worker.main()

    # Global gate MUST happen before Neon construction and before claim_sim_shard.
    # A blocked manifest therefore cannot drain, reclassify, or otherwise mutate
    # the pending queue.
    if not ranking_ready:
        print(json.dumps({
            "rankingReady": False,
            "queue": "blocked",
            "claimed": 0,
            "databaseCalls": 0,
            "reason": "canonical policy manifest has rankingReady=false",
        }, sort_keys=True), flush=True)
        return 0

    argv, runner_id = _runner_id(original_argv)
    sys.argv = [sys.argv[0], *argv]
    runner_kind = _runner_kind()
    api = worker.NeonDataApi(
        os.environ.get("NEON_DATA_API", ""),
        os.environ.get("NEON_DATA_API_TOKEN", ""),
    )
    with RunnerHeartbeat(
        api,
        runner_id=runner_id,
        runner_kind=runner_kind,
        manifest_sha256=manifest_sha256,
        ranking_ready=True,
    ) as heartbeat:
        result = worker.main()
        if heartbeat.error is not None:
            raise worker.QueueError(f"runner heartbeat failed: {heartbeat.error}")
        return result


if __name__ == "__main__":
    raise SystemExit(main())
