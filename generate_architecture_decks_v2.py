#!/usr/bin/env python3
"""Root-level import shim for GitHub Actions inline analysis snippets.

The canonical generator lives under engine-tests/, which is not importable by
name from repository-root `python3 -` snippets. This shim loads that file and
re-exports SPECS without duplicating experiment definitions.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "engine-tests" / "generate_architecture_decks_v2.py"
_SPEC = importlib.util.spec_from_file_location("_kinnan_architecture_generator", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load architecture generator at {_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

SPECS = _MODULE.SPECS
