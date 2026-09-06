#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import kinnan_planning_context as transport
import kinnan_v9_forge_canary as forge
import local_queue_runner as queue
import manabrew_pilot_v9 as pilot
import run_kinnan_sim as canonical
import sim_v2_worker as worker
from kinnan_semantics_v9 import SemanticError


def valid_context() -> dict:
    return {
        "availableRoles": ["engine-b"],
        "witnessedLineIds": [],
        "threatenedLineIds": [],
        "branches": [
            {
                "planId": "route-a",
                "requiredRoles": ["engine-a", "outlet-a"],
            },
            {
                "planId": "route-b",
                "requiredRoles": ["engine-b", "outlet-b"],
            },
        ],
    }


class PlanningContextTransportTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.get(transport.PLANNING_CONTEXT_ENV)
        os.environ.pop(transport.PLANNING_CONTEXT_ENV, None)

    def tearDown(self):
        if self.previous is None:
            os.environ.pop(transport.PLANNING_CONTEXT_ENV, None)
        else:
            os.environ[transport.PLANNING_CONTEXT_ENV] = self.previous

    def test_queue_config_reaches_worker_and_live_action_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            path = queue._write_planning_context(
                {"planningContext": valid_context()},
                Path(directory),
            )
            installed = canonical._install_planning_context_file(str(path))

            class Runner:
                pass

            runner = Runner()
            worker_context = worker.install_worker_planning_context(runner)
            self.assertEqual(installed, worker_context)
            self.assertEqual(worker_context, runner._V9_PLANNING_CONTEXT)

            raw_snapshot = {
                "phase": "main1",
                "step": "main1",
                "priorityPlayerId": "player-0",
            }
            snapshot = forge._decision_snapshot(
                raw_snapshot,
                runner._V9_PLANNING_CONTEXT,
            )
            chosen = pilot.choose_action(
                [
                    {"id": "route-a-engine", "type": "cast", "providesRoles": ["engine-a"]},
                    {"id": "route-b-outlet", "type": "cast", "providesRoles": ["outlet-b"]},
                ],
                snapshot,
                player_id="player-0",
            )
            self.assertEqual(chosen["id"], "route-b-outlet")
            self.assertNotIn("planningContext", raw_snapshot)
            self.assertEqual(snapshot["planningContext"], installed)

            base_key = dict(
                engine_id="engine",
                pilot_version="pilot",
                optimizer_id="optimizer",
                execution_profile="profile",
                deck_sha="deck",
                pod_sha="pod",
                mode="screen",
                pod="screen",
                seed=1,
                seat=0,
                max_round=4,
            )
            self.assertNotEqual(
                worker.cache_key(**base_key),
                worker.cache_key(
                    **base_key,
                    planning_context_sha256=transport.planning_context_hash(installed),
                ),
            )

    def test_malformed_or_oversized_queue_plan_becomes_needs_pilot(self):
        malformed = valid_context()
        malformed["availableRoles"] = ["Invalid Role"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(queue.NeedsPilot, "invalid role ID"):
                queue._write_planning_context(
                    {"planningContext": malformed},
                    Path(directory),
                )

            oversized = valid_context()
            oversized["branches"] = [
                {"planId": f"route-{index}", "requiredRoles": ["engine"]}
                for index in range(33)
            ]
            with self.assertRaisesRegex(queue.NeedsPilot, "1-32 branches"):
                queue._write_planning_context(
                    {"planningContext": oversized},
                    Path(directory),
                )

    def test_direct_canonical_or_adapter_input_hard_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps({"branches": "not-an-array"}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "invalid --planning-context-file"):
                canonical._install_planning_context_file(str(path))

        with self.assertRaises(SemanticError):
            forge._decision_snapshot(
                {"step": "main1"},
                {"branches": [{"planId": "route", "requiredRoles": ["bad role"]}]},
            )

    def test_queue_rejects_bad_plan_before_runtime_lookup(self):
        class Heartbeat:
            lost_event = None

        spec = {
            "shard_id": "bad-plan",
            "experiment_config": {"planningContext": {"branches": []}},
            "requested_games": 1,
            "seed_start": 10,
            "seed_end": 10,
        }
        with self.assertRaises(queue.NeedsPilot):
            queue.execute_shard(spec, Heartbeat())

    def test_queue_passes_context_file_and_verifies_worker_hash(self):
        captured: dict = {}

        class Heartbeat:
            lost_event = threading.Event()

        class FinishedProcess:
            returncode = 0

            def __init__(self, command, **_kwargs):
                captured["command"] = command
                context_path = Path(command[command.index("--planning-context-file") + 1])
                context_hash = transport.planning_context_hash(
                    transport.load_planning_context_file(context_path)
                )
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps([{
                    "seed": 10,
                    "telemetryV3Complete": True,
                    "variantDeckSha256": "deck-hash",
                    "planningContextSha256": context_hash,
                }]), encoding="utf-8")

            def poll(self):
                return 0

        spec = {
            "shard_id": "planned-shard",
            "experiment_config": {
                "engineId": "engine",
                "planningContext": valid_context(),
            },
            "requested_games": 1,
            "seed_start": 10,
            "seed_end": 10,
            "mode": "screen",
            "variant_code": "PENDING",
            "seat": 0,
            "pod": "screen",
            "deck_sha256": "deck-hash",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            here = root / "engine-tests"
            here.mkdir()
            jar = root / "harness.jar"
            jar.write_bytes(b"jar")
            forge_home = root / "forge"
            forge_home.mkdir()
            with ExitStack() as stack:
                stack.enter_context(patch.object(queue, "HERE", here))
                stack.enter_context(patch.object(queue, "ROOT", root))
                stack.enter_context(patch.object(queue.subprocess, "Popen", FinishedProcess))
                stack.enter_context(patch.dict(os.environ, {
                    "MANABREW_HARNESS_JAR": str(jar),
                    "MANABREW_FORGE_HOME": str(forge_home),
                }))
                results = queue.execute_shard(spec, Heartbeat())
        self.assertEqual(results[0]["planningContextSha256"], transport.planning_context_hash(valid_context()))
        self.assertIn("--planning-context-file", captured["command"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
