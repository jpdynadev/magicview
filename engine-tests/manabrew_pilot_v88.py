#!/usr/bin/env python3
"""Compatibility wrapper for manabrew_pilot_v8.

Pinned Manabrew exposes chooseColor options as full names ("Blue", "Green", ...),
while the v8 policy internally uses Magic shorthand ("U", "G", ...). Translate
only the protocol response at the boundary; all policy decisions remain unchanged.
"""
from __future__ import annotations

import manabrew_pilot_v8 as v8


_COLOR_NAMES = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "C": "Colorless",
}

_original_response = v8.base.response_for


def protocol_safe_response(prompt, snapshot, deck, player):
    response = _original_response(prompt, snapshot, deck, player)
    inp = (prompt or {}).get("input") or {}
    if inp.get("type") != "chooseColor" or not response:
        return response
    output = response.get("output") or {}
    chosen = output.get("chosenColors") or {}
    if not chosen:
        return response
    translated = {_COLOR_NAMES.get(str(color), str(color)): amount for color, amount in chosen.items()}
    fixed = dict(response)
    fixed_output = dict(output)
    fixed_output["chosenColors"] = translated
    fixed["output"] = fixed_output
    return fixed


v8.base.response_for = protocol_safe_response

if __name__ == "__main__":
    raise SystemExit(v8.main())
