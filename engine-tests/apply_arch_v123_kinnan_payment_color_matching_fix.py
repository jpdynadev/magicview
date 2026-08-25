#!/usr/bin/env python3
"""Apply v1.23 payment-stage color-source matching for Kinnan {5}{G}{U}.

v1.22 still reproduced seat=1 seed=5010140 because the first payManaCost
prompt offered Waterlogged Grove as both G and U but no second explicit colored
source.  The payment policy selected U from Grove, then only ambiguous Fellwar
Stone remained, which chose White and forced cancel/retry.

v1.23 fixes the failure at the payment prompt itself.  Before spending any mana
for Kinnan's activation, missing colored pips must be matchable to distinct
currently-advertised physical sources.  A single flexible source cannot satisfy
both G and U unless one pip is already safely floating.  Ambiguous mana actions
without producedMana are never invented as colored sources.  Forge remains the
legality/payment authority.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.23-adversarial" in text and "_v123_payment_response" in text:
    print('v1.23 Kinnan payment color matching already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.22-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.22 pilot identity not found; apply v1.12-v1.22 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.23-adversarial'", 1)

append = r'''

# v1.23: validate colored source matching at the actual payManaCost prompt.
_V122_RESPONSE = runner.base.response_for


def _v123_explicit_color_sources(inp: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for action in inp.get('actions', []) or []:
        if not (action.get('isManaAbility') or action.get('type') == 'activateManaAbility'):
            continue
        source = str(action.get('cardId') or action.get('card_id') or '')
        if not source:
            continue
        colors: set[str] = set()
        for item in action.get('producedMana') or []:
            try:
                amount = max(0, int((item or {}).get('amount') or 0))
            except (AttributeError, TypeError, ValueError):
                amount = 0
            if amount > 0:
                colors.add(_v118_color_token((item or {}).get('color')))
        if colors:
            out.setdefault(source, set()).update(colors)
    return out


def _v123_missing_colors_matchable(snapshot: dict[str, Any], inp: dict[str, Any], player: int) -> bool:
    floating = _v118_floating_mana(snapshot, player)
    missing = [c for c in ('G', 'U') if floating.get(c, 0) < 1]
    if not missing:
        return True
    sources = _v123_explicit_color_sources(inp)
    if len(missing) == 1:
        wanted = missing[0]
        return any(wanted in colors for colors in sources.values())
    green = [src for src, colors in sources.items() if 'G' in colors]
    blue = [src for src, colors in sources.items() if 'U' in colors]
    return any(gsrc != usrc for gsrc in green for usrc in blue)


def _v123_payment_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    inp = prompt.get('input') or {}
    if deck == 'Kinnan' and inp.get('type') == 'payManaCost':
        card_name = str(inp.get('cardName') or '')
        cost = str(inp.get('manaCost') or '').replace(' ', '').upper()
        if card_name == 'Kinnan, Bonder Prodigy' and ('{5}{G}{U}' in cost or '{5}{U}{G}' in cost):
            if not bool(inp.get('canConfirmFromPool')) and not _v123_missing_colors_matchable(snapshot, inp, player):
                return {'type': 'payManaCost', 'output': {'type': 'cancel'}}
    return _V122_RESPONSE(prompt, snapshot, deck, player)


runner.base.response_for = _v123_payment_response
arch.base.response_for = _v123_payment_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.23-adversarial Kinnan payment color matching guard')
