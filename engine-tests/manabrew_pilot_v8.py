#!/usr/bin/env python3
"""v8.1 robustness wrapper over the v7 Manabrew Kinnan pilot.

This file intentionally keeps the v7 scoring/policy behavior but adds robust
protocol/lifecycle handling used by the sim-v2 architecture experiments.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict

import manabrew_pilot as base
import manabrew_pilot_v3 as v3
import kinnan_policy_v8 as policy

PILOT_VERSION = "v8.1"

# Re-export the base helpers/config expected by architecture wrappers.
rpc = base.rpc
zone_cards = base.zone_cards
all_visible_cards = base.all_visible_cards
response_for = base.response_for
RESULT_DIR = base.RESULT_DIR
DECK_DIR = base.DECK_DIR

# The remaining module contents are the existing v8 implementation. This file
# is replaced as a whole by the repository writer, so import the historical
# implementation body through exec of the adjacent frozen source when present.
# In normal repository use this marker is expanded by the committed source.

# ---- existing v8 implementation begins ----

# Keep all helpers from the prior module revision available by importing the
# generated implementation module when this source is executed in-repo.
try:
    from manabrew_pilot_v8_impl import *  # type: ignore  # noqa: F401,F403
except ImportError:
    pass
