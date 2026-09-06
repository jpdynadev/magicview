#!/usr/bin/env python3
"""Lease queued Kinnan shards from Neon and execute them on this machine.

The scheduler creates experiment/variant/shard rows. This worker owns compute,
but never invents policy support: every run passes the semantic preflight and
the canonical ranking launcher. Result ingestion and shard completion happen in
one database RPC so a process crash cannot publish a partial shard.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from run_kinnan_sim import validate_submitted_deck  # noqa: E402


class QueueError(RuntimeError):
    pass


class NeedsPilot(QueueError):
    pass


class LeaseLost(QueueError):
    pass


class NeonDataApi:
    def __init__(self, base_url: str, token: str, timeout: int = 30):
        if not base_url or not token:
            raise QueueError("NEON_DATA_API and NEON_DATA_API_TOKEN are required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        request = urllib.request.Request(
            f"{self.base_url}/rpc/{name}",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise QueueError(f"Neon RPC {name} failed ({exc.code}): {detail[:2000]}") from exc
        except urllib.error.URLError as exc:
            raise QueueError(f"Neon RPC {name} failed: {exc.reason}") from exc
        return json.loads(body) if body else None


def _rpc_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, list) and len(value) == 1:
        row = value[0]
        if isinstance(row, bool):
            return row
        if isinstance(row, dict) and len(row) == 1:
            return bool(next(iter(row.values())))
    if isinstance(value, dict) and len(value) == 1:
        return bool(next(iter(value.values())))
    return False


def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def semantic_preflight() -> None:
    report = HERE / "results" / "local-policy-parity-v2-components.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    run_checked([sys.executable, str(HERE / "test_kinnan_semantics_v9.py")])
    run_checked([
        sys.executable,
        str(HERE / "validate_kinnan_policy_parity_v2.py"),
        "--component-only",
        "--report",
        str(report),
    ])
    run_checked([sys.executable, str(HERE / "run_kinnan_sim.py"), "--purpose", "component-canary"])


def load_manifest() -> dict[str, Any]:
    return json.loads((HERE / "kinnan_policy_parity_manifest_v2.json").read_text(encoding="utf-8"))


def require_supported_capabilities(spec: dict[str, Any], manifest: dict[str, Any]) -> None:
    required = list(spec.get("required_capabilities") or [])
    capabilities = manifest.get("capabilities") or {}
    missing = [name for name in required if name not in capabilities]
    unsupported = [
        name for name in required
        if name in capabilities and not bool(capabilities[name].get("productionSupported"))
    ]
    if missing:
        raise NeedsPilot(f"unknown required pilot capabilities: {', '.join(sorted(missing))}")
    if unsupported:
        raise NeedsPilot(f"pilot capabilities are not production-supported: {', '.join(sorted(unsupported))}")
    if not manifest.get("rankingReady"):
        raise NeedsPilot("canonical policy manifest has rankingReady=false")


def _write_submitted_deck(spec: dict[str, Any], directory: Path) -> Path | None:
    deck_text = spec.get("deck_text")
    if deck_text is None:
        return None
    if not isinstance(deck_text, str) or not deck_text.strip():
        raise NeedsPilot("submitted deck text is empty")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "submitted.dck"
    path.write_text(deck_text, encoding="utf-8", newline="\n")
    try:
        validate_submitted_deck(path)
    except (OSError, RuntimeError, UnicodeError) as exc:
        raise NeedsPilot(f"submitted deck failed strict full-99 validation: {exc}") from exc
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = str(spec.get("deck_sha256") or "")
    if actual != expected:
        raise NeedsPilot(f"submitted deck hash mismatch: expected {expected}, got {actual}")
    return path


def _int_config(config: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError) as exc:
        raise QueueError(f"experiment config {key} must be an integer") from exc
    if not low <= value <= high:
        raise QueueError(f"experiment config {key} must be between {low} and {high}")
    return value


@dataclass
class Heartbeat:
    api: NeonDataApi
    shard_id: str
    lease_token: str
    lease_seconds: int

    def __post_init__(self) -> None:
        self.stop_event = threading.Event()
        self.lost_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, name=f"lease-{self.shard_id}", daemon=True)

    def _loop(self) -> None:
        interval = max(20, self.lease_seconds // 3)
        while not self.stop_event.wait(interval):
            try:
                value = self.api.rpc("renew_sim_shard_lease", {
                    "p_shard_id": self.shard_id,
                    "p_lease_token": self.lease_token,
                    "p_lease_seconds": self.lease_seconds,
                })
                if not _rpc_boolean(value):
                    self.lost_event.set()
                    return
            except QueueError:
                self.lost_event.set()
                return

    def __enter__(self) -> "Heartbeat":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)


def execute_shard(spec: dict[str, Any], heartbeat: Heartbeat) -> list[dict[str, Any]]:
    shard_id = str(spec["shard_id"])
    config = dict(spec.get("experiment_config") or {})
    requested = int(spec["requested_games"])
    seed_start = int(spec["seed_start"])
    seed_end = int(spec["seed_end"])
    if requested <= 0 or seed_end - seed_start + 1 != requested:
        raise QueueError("shard seed range must exactly match requested_games")

    jar = os.environ.get("MANABREW_HARNESS_JAR", "")
    forge_home = os.environ.get("MANABREW_FORGE_HOME", "")
    if not jar or not Path(jar).is_file():
        raise QueueError("MANABREW_HARNESS_JAR must name the built harness jar")
    if not forge_home or not Path(forge_home).is_dir():
        raise QueueError("MANABREW_FORGE_HOME must name the Forge GUI directory")

    run_dir = HERE / "local-runs" / shard_id
    run_dir.mkdir(parents=True, exist_ok=True)
    deck_path = _write_submitted_deck(spec, run_dir)
    output = run_dir / "results.json"
    command = [
        sys.executable, str(HERE / "run_kinnan_sim.py"), "--purpose", "ranking", "--",
        str(Path(jar).resolve()), str(Path(forge_home).resolve()),
        "--mode", str(spec["mode"]), "--variant", str(spec["variant_code"]),
        "--fixed-seat", str(spec["seat"]), "--seeds",
        *[str(seed) for seed in range(seed_start, seed_end + 1)],
        "--max-round", str(_int_config(config, "maxRound", 4, 1, 20)),
        "--max-prompts", str(_int_config(config, "maxPrompts", 7000, 100, 50000)),
        "--max-seconds", str(_int_config(config, "maxSeconds", 240, 10, 3600)),
        "--jvm-reuse", str(_int_config(config, "jvmReuse", 1, 1, 20)),
        "--xmx", str(config.get("xmx", "1280m")), "--xms", str(config.get("xms", "192m")),
        "--cache-dir", str(HERE / ".sim-cache" / "local-v9"),
        "--retain-traces", str(config.get("retainTraces", "failures")),
        "--engine-id", str(config.get("engineId") or os.environ.get("MANABREW_REF") or ""),
        "--output", str(output),
    ]
    if not command[command.index("--engine-id") + 1]:
        raise QueueError("experiment config engineId or MANABREW_REF is required")
    if deck_path is not None:
        command.extend(["--deck-file", str(deck_path)])

    env = os.environ.copy()
    env["CEDH_POD"] = str(spec["pod"])
    env.setdefault("SIM_V2_EARLY_SUCCESS", "0")
    env.setdefault("SIM_V2_EXACT_DEADLINE", "0")
    env.setdefault("SIM_V2_TRACE", "0")
    process = subprocess.Popen(command, cwd=ROOT, env=env)
    while process.poll() is None:
        if heartbeat.lost_event.wait(1):
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
            raise LeaseLost(f"lease lost while executing shard {shard_id}")
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command)
    if heartbeat.lost_event.is_set():
        raise LeaseLost(f"lease lost before ingesting shard {shard_id}")

    results = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(results, list) or len(results) != requested:
        raise QueueError(f"worker produced {len(results) if isinstance(results, list) else 'non-list'} results; expected {requested}")
    expected_seeds = set(range(seed_start, seed_end + 1))
    actual_seeds = {int(item.get("seed", -1)) for item in results if isinstance(item, dict)}
    if actual_seeds != expected_seeds:
        raise QueueError("worker result seeds do not match the leased shard")
    for item in results:
        if not item.get("telemetryV3Complete"):
            raise QueueError("worker result lacks complete full-99 v3 telemetry")
        if item.get("variantDeckSha256") != spec.get("deck_sha256"):
            raise QueueError("worker result deck hash does not match the queued variant")
    return results


def claim_one(api: NeonDataApi, runner_id: str, lease_seconds: int) -> dict[str, Any] | None:
    value = api.rpc("claim_sim_shard", {
        "p_runner_id": runner_id,
        "p_lease_seconds": lease_seconds,
    })
    if value in (None, []):
        return None
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise QueueError(f"unexpected claim response: {value!r}")
    return value[0]


def fail_claim(api: NeonDataApi, spec: dict[str, Any], error: Exception, *, needs_pilot: bool) -> None:
    value = api.rpc("fail_sim_shard", {
        "p_shard_id": spec["shard_id"],
        "p_lease_token": spec["lease_token"],
        "p_error": f"{type(error).__name__}: {error}",
        "p_needs_pilot": needs_pilot,
    })
    if not _rpc_boolean(value):
        raise LeaseLost(f"could not fail shard {spec['shard_id']}; lease no longer owned")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run queued Kinnan simulation shards locally")
    parser.add_argument("--max-shards", type=int, default=1)
    parser.add_argument("--lease-seconds", type=int, default=300)
    parser.add_argument("--runner-id", default=f"{socket.gethostname()}-{os.getpid()}")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run semantic gates and report configuration without claiming work",
    )
    args = parser.parse_args()
    if args.max_shards < 1:
        parser.error("--max-shards must be positive")

    semantic_preflight()
    manifest = load_manifest()
    if args.dry_run:
        required_env = (
            "NEON_DATA_API", "NEON_DATA_API_TOKEN", "MANABREW_REF",
            "MANABREW_HARNESS_JAR", "MANABREW_FORGE_HOME",
        )
        print(json.dumps({
            "dryRun": True,
            "semanticPreflight": "passed",
            "rankingReady": bool(manifest.get("rankingReady")),
            "configured": {name: bool(os.environ.get(name)) for name in required_env},
            "databaseCalls": 0,
        }, sort_keys=True), flush=True)
        return 0
    api = NeonDataApi(
        os.environ.get("NEON_DATA_API", ""),
        os.environ.get("NEON_DATA_API_TOKEN", ""),
    )
    processed = 0
    while processed < args.max_shards:
        spec = claim_one(api, args.runner_id, args.lease_seconds)
        if spec is None:
            print(json.dumps({"queue": "empty", "processed": processed}), flush=True)
            break
        try:
            require_supported_capabilities(spec, manifest)
            with Heartbeat(api, str(spec["shard_id"]), str(spec["lease_token"]), args.lease_seconds) as heartbeat:
                results = execute_shard(spec, heartbeat)
                completed = api.rpc("finish_sim_shard", {
                    "p_shard_id": spec["shard_id"],
                    "p_lease_token": spec["lease_token"],
                    "p_results": results,
                })
                if not _rpc_boolean(completed):
                    raise LeaseLost(f"completion rejected for shard {spec['shard_id']}")
            print(json.dumps({"shard": spec["shard_id"], "status": "complete"}), flush=True)
        except NeedsPilot as exc:
            fail_claim(api, spec, exc, needs_pilot=True)
            print(json.dumps({"shard": spec["shard_id"], "status": "needs_pilot", "reason": str(exc)}), flush=True)
        except LeaseLost:
            raise
        except Exception as exc:
            fail_claim(api, spec, exc, needs_pilot=False)
            raise
        processed += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
