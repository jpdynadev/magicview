#!/usr/bin/env python3
import json, sys
import manabrew_pilot as base
import manabrew_pilot_v3 as v3

# Patch the shared response policy so every chooseColor response is selected from
# the exact validColors list supplied by Manabrew's protocol.
_original_response_for = base.response_for


def _choose_color_response(inp, deck):
    valid = list(inp.get('validColors') or [])
    if not valid:
        raise RuntimeError(f"chooseColor prompt supplied no validColors: {json.dumps(inp)[:1200]}")
    amount = int(inp.get('amount', 1) or 1)
    repeat_allowed = bool(inp.get('repeatAllowed', False))

    def blue_score(value):
        token = str(value).strip().lower()
        return 1 if token in {'u', 'blue'} else 0

    ordered = sorted(valid, key=blue_score, reverse=(deck == 'Kinnan'))
    chosen = {}
    if repeat_allowed:
        chosen[ordered[0]] = amount
    else:
        if amount > len(ordered):
            raise RuntimeError(f"chooseColor amount {amount} exceeds distinct valid colors {ordered}")
        for color in ordered[:amount]:
            chosen[color] = chosen.get(color, 0) + 1
    return {'type':'chooseColor','output':{'type':'colorDecision','chosenColors':chosen}}


def patched_response_for(prompt, snap, deck, player):
    inp = prompt.get('input') or {}
    if inp.get('type') == 'chooseColor':
        return _choose_color_response(inp, deck)
    return _original_response_for(prompt, snap, deck, player)


base.response_for = patched_response_for


def main():
    if len(sys.argv) < 3:
        print('usage: manabrew_pilot_v4.py HARNESS_JAR FORGE_HOME [seed ...]', file=sys.stderr)
        return 2
    jar, home = sys.argv[1], sys.argv[2]
    seeds = [int(x) for x in sys.argv[3:]] or [101, 202, 303]
    results = []
    for seed in seeds:
        try:
            r = v3.run_game(jar, home, seed)
        except Exception as exc:
            r = {'seed': seed, 'status': 'crash', 'error': repr(exc)}
        print(json.dumps(r, sort_keys=True), flush=True)
        results.append(r)
    (base.RESULT_DIR / 'pilot-summary.json').write_text(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
