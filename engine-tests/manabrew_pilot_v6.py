#!/usr/bin/env python3
import json, sys
import manabrew_pilot as base

# Save pristine base functions before importing the layered pilot modules that
# monkey-patch them.
_original_keep_hand = base.keep_hand
_original_action_score = base.action_score

import manabrew_pilot_v3 as v3
import manabrew_pilot_v4  # legal chooseColor patch
import manabrew_pilot_v5 as v5  # phase-aware policy definitions


def fixed_keep_hand(deck, hand, mull_count):
    # v5.phase_aware_keep only needs the original base keep function in its
    # generic fallback branch. Temporarily expose that original to prevent
    # self-recursion after monkey-patching.
    saved = base.keep_hand
    base.keep_hand = _original_keep_hand
    try:
        return v5.phase_aware_keep(deck, hand, mull_count)
    finally:
        base.keep_hand = saved


def fixed_action_score(deck, action, snap, player):
    # Same pattern for v5._base_or_minus(): while the phase-aware scorer is
    # executing, make its fallback call the pristine v1 scorer instead of
    # re-entering itself.
    saved = base.action_score
    base.action_score = _original_action_score
    try:
        return v5.phase_aware_action_score(deck, action, snap, player)
    finally:
        base.action_score = saved


base.keep_hand = fixed_keep_hand
base.action_score = fixed_action_score


def main():
    if len(sys.argv) < 3:
        print('usage: manabrew_pilot_v6.py HARNESS_JAR FORGE_HOME [seed ...]', file=sys.stderr)
        return 2
    jar, home = sys.argv[1], sys.argv[2]
    seeds = [int(x) for x in sys.argv[3:]] or [101, 202, 303]
    results = []
    for seed in seeds:
        try:
            r = v3.run_game(jar, home, seed, max_prompts=1800, max_round=5)
        except Exception as exc:
            r = {'seed': seed, 'status': 'crash', 'error': repr(exc)}
        print(json.dumps(r, sort_keys=True), flush=True)
        results.append(r)
    (base.RESULT_DIR / 'pilot-summary.json').write_text(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
