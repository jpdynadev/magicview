#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

import local_queue_runner_safe as safe


class SafeRunnerGateTests(unittest.TestCase):
    def test_ranking_blocked_exits_before_neon_or_worker(self) -> None:
        output = io.StringIO()
        with mock.patch.object(safe, "_manifest", return_value=({"rankingReady": False}, "manifest-sha")), \
             mock.patch.object(safe.worker, "NeonDataApi", side_effect=AssertionError("Neon must not be constructed")), \
             mock.patch.object(safe.worker, "main", side_effect=AssertionError("canonical worker must not run")), \
             mock.patch.object(sys, "argv", ["local_queue_runner_safe.py"]), \
             redirect_stdout(output):
            self.assertEqual(safe.main(), 0)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["rankingReady"])
        self.assertEqual(payload["claimed"], 0)
        self.assertEqual(payload["databaseCalls"], 0)

    def test_dry_run_delegates_without_queue_gate(self) -> None:
        with mock.patch.object(safe, "_manifest", return_value=({"rankingReady": False}, "manifest-sha")), \
             mock.patch.object(safe.worker, "main", return_value=17) as worker_main, \
             mock.patch.object(sys, "argv", ["local_queue_runner_safe.py", "--dry-run"]):
            self.assertEqual(safe.main(), 17)
            worker_main.assert_called_once_with()

    def test_runner_kind_is_bounded(self) -> None:
        with mock.patch.dict(os.environ, {"KINNAN_RUNNER_KIND": "github"}, clear=False):
            self.assertEqual(safe._runner_kind(), "github")
        with mock.patch.dict(os.environ, {"KINNAN_RUNNER_KIND": "other"}, clear=False):
            with self.assertRaises(SystemExit):
                safe._runner_kind()


if __name__ == "__main__":
    unittest.main()
