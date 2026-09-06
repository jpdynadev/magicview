#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import local_queue_runner as queue
from run_kinnan_sim import validate_submitted_deck


def deck_text(main_count: int = 99) -> str:
    cards = "\n".join(f"1 Test Card {number}" for number in range(main_count))
    return f"[Commander]\n1 Kinnan, Bonder Prodigy\n\n[Main]\n{cards}\n"


class LocalQueueRunnerTests(unittest.TestCase):
    def test_submitted_deck_requires_exact_unique_99(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deck.dck"
            path.write_text(deck_text(), encoding="utf-8")
            digest, cards = validate_submitted_deck(path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            self.assertEqual(99, len(cards))

            path.write_text(deck_text(98), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "99 unique"):
                validate_submitted_deck(path)

    def test_canonical_launcher_registers_valid_submitted_deck(self):
        class Runner:
            VARIANT_FILES = {}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deck.dck"
            path.write_text(deck_text(), encoding="utf-8")
            from run_kinnan_sim import _register_submitted_deck

            runner = Runner()
            _register_submitted_deck(
                runner, ["--variant", "SUBMISSION_TEST"], str(path)
            )
            self.assertEqual(str(path.resolve()), runner.VARIANT_FILES["SUBMISSION_TEST"])

    def test_unknown_or_unsupported_capability_needs_pilot(self):
        manifest = {
            "rankingReady": True,
            "capabilities": {"copy_choice": {"productionSupported": False}},
        }
        with self.assertRaisesRegex(queue.NeedsPilot, "not production-supported"):
            queue.require_supported_capabilities(
                {"required_capabilities": ["copy_choice"]}, manifest
            )
        with self.assertRaisesRegex(queue.NeedsPilot, "unknown"):
            queue.require_supported_capabilities(
                {"required_capabilities": ["invented_line"]}, manifest
            )

    def test_ranking_manifest_remains_fail_closed(self):
        manifest = {"rankingReady": False, "capabilities": {}}
        with self.assertRaisesRegex(queue.NeedsPilot, "rankingReady=false"):
            queue.require_supported_capabilities({"required_capabilities": []}, manifest)

    def test_claim_response_and_boolean_shapes(self):
        class Api:
            def __init__(self, response):
                self.response = response

            def rpc(self, _name, _payload):
                return self.response

        self.assertIsNone(queue.claim_one(Api([]), "runner", 300))
        claimed = queue.claim_one(Api([{"shard_id": "abc"}]), "runner", 300)
        self.assertEqual("abc", claimed["shard_id"])
        self.assertTrue(queue._rpc_boolean(True))
        self.assertTrue(queue._rpc_boolean([{"finish_sim_shard": True}]))
        self.assertFalse(queue._rpc_boolean([]))

    def test_invalid_shard_range_fails_before_runtime_lookup(self):
        class Heartbeat:
            lost_event = None

        spec = {
            "shard_id": "abc",
            "experiment_config": {},
            "requested_games": 3,
            "seed_start": 10,
            "seed_end": 11,
        }
        with self.assertRaisesRegex(queue.QueueError, "seed range"):
            queue.execute_shard(spec, Heartbeat())


if __name__ == "__main__":
    unittest.main()
