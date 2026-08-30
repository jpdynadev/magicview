#!/usr/bin/env python3
"""Apply v1.18 colored-affordability guard for Kinnan's {5}{G}{U} activation.

The v1.17 tournament forensic for canonical key seat=1 seed=5010140 showed a
reproducible activate->partial-payment->cancel loop.  The prior Kinnan guard
checked only total mana capacity.  On the failing state there were seven-plus
nominal mana, but only one source (Waterlogged Grove) could produce either G or
U while Fellwar Stone's actual choice was White.  The pilot repeatedly selected
Kinnan, could not satisfy both colored pips, cancelled payment, and retried.

v1.18 is deliberately narrow: before accepting Kinnan's {5}{G}{U} activation,
require an optimistic *source-aware* way to cover both colored pips from current
floating mana plus explicitly advertised colored mana abilities.  Unspecified
mana abilities still count toward generic capacity but are not assumed to make
G/U.  Forge remains the legality/payment authority.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.18-adversarial" in text and "_v118_guard_kinnan_colored_affordability" in text:
    print('v1.18 Kinnan colored-affordability repair already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.17-fourarch-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.17 pilot identity not found; apply v1.12-v1.17 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.18-adversarial'", 1)

append = r'''

# v1.18: source-aware colored affordability for Kinnan {5}{G}{U}.
_V117_RESPONSE = runner.base.response_for


def _v118_color_token(value: Any) -> str:
    token = str(value or '').strip().upper()
    aliases = {
        'GREEN': 'G', 'G': 'G',
        'BLUE': 'U', 'U': 'U',
        'WHITE': 'W', 'W': 'W',
        'BLACK': 'B', 'B': 'B',
        'RED': 'R', 'R': 'R',
        'COLORLESS': 'C', 'C': 'C',
    }
    return aliases.get(token, token)


def _v118_floating_mana(snapshot: dict[str, Any], player: int) -> dict[str, int]:
    wanted = f'player-{player}'
    out: dict[str, int] = {}
    for item in snapshot.get('players', []) or []:
        if str(item.get('id') or '') != wanted:
            continue
        for raw, value in (item.get('manaPool') or {}).items():
            try:
                amount = max(0, int(value or 0))
            except (TypeError, ValueError):
                continue
            color = _v118_color_token(raw)
            out[color] = out.get(color, 0) + amount
        break
    return out


def _v118_source_color_options(inp: dict[str, Any]) -> dict[str, tuple[set[str], int]]:
    """Return advertised color options and one-shot capacity per physical source.

    Multiple G/U action choices for one permanent are alternatives, not separate
    mana sources, so they are merged by cardId.  Missing producedMana remains
    generic-only here; it may still satisfy the five generic mana via the older
    total-capacity guard, but we do not invent a colored capability.
    """
    options: dict[str, set[str]] = {}
    capacity: dict[str, int] = {}
    for action in inp.get('actions', []) or []:
        if not (action.get('isManaAbility') or action.get('type') in {'activateManaAbility'}):
            continue
        source = str(action.get('cardId') or action.get('card_id') or '')
        if not source:
            continue
        produced = action.get('producedMana') or []
        amount = 0
        colors: set[str] = set()
        for item in produced:
            try:
                n = max(0, int((item or {}).get('amount') or 0))
            except (AttributeError, TypeError, ValueError):
                n = 0
            if n <= 0:
                continue
            amount += n
            color = _v118_color_token((item or {}).get('color'))
            if color:
                colors.add(color)
        # Keep unspecified mana abilities as generic capacity only.
        if amount <= 0:
            amount = _mana_action_capacity(action)
        options.setdefault(source, set()).update(colors)
        capacity[source] = max(capacity.get(source, 0), amount)
    return {source: (options.get(source, set()), capacity.get(source, 0)) for source in capacity}


def _v118_can_cover_gu(snapshot: dict[str, Any], inp: dict[str, Any], player: int) -> bool:
    floating = _v118_floating_mana(snapshot, player)
    need_g = 0 if floating.get('G', 0) >= 1 else 1
    need_u = 0 if floating.get('U', 0) >= 1 else 1
    if not need_g and not need_u:
        return True

    sources = _v118_source_color_options(inp)
    if need_g and not need_u:
        return any(cap >= 1 and 'G' in colors for colors, cap in sources.values())
    if need_u and not need_g:
        return any(cap >= 1 and 'U' in colors for colors, cap in sources.values())

    green = [(src, cap) for src, (colors, cap) in sources.items() if cap >= 1 and 'G' in colors]
    blue = [(src, cap) for src, (colors, cap) in sources.items() if cap >= 1 and 'U' in colors]
    for gsrc, gcap in green:
        for usrc, ucap in blue:
            if gsrc != usrc:
                return True
            if gcap >= 2 and ucap >= 2:
                return True
    return False


def _v118_guard_kinnan_colored_affordability(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int,
    answer: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if deck != 'Kinnan':
        return answer
    inp = prompt.get('input') or {}
    if inp.get('type') != 'chooseAction':
        return answer
    output = (answer or {}).get('output') or {}
    if output.get('type') != 'act' or not output.get('actionId'):
        return answer
    chosen_id = str(output['actionId'])
    chosen = next(
        (action for action in (inp.get('actions') or []) if str(action.get('id') or '') == chosen_id),
        None,
    )
    if not chosen or chosen.get('type') != 'activateAbility':
        return answer
    if runner._action_card(chosen, snapshot) != 'Kinnan, Bonder Prodigy':
        return answer
    normalized = (str(chosen.get('cost') or '') + str(chosen.get('description') or '')).replace(' ', '').upper()
    if '{5}{G}{U}' not in normalized and '{5}{U}{G}' not in normalized:
        return answer
    if _v118_can_cover_gu(snapshot, inp, player):
        return answer

    filtered_prompt = dict(prompt)
    filtered_input = dict(inp)
    filtered_input['actions'] = [
        action for action in (inp.get('actions') or [])
        if str(action.get('id') or '') != chosen_id
    ]
    filtered_prompt['input'] = filtered_input
    retry = _V117_RESPONSE(filtered_prompt, snapshot, deck, player)
    if retry is not None:
        return retry
    return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}


def _v118_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    answer = _V117_RESPONSE(prompt, snapshot, deck, player)
    return _v118_guard_kinnan_colored_affordability(prompt, snapshot, deck, player, answer)


runner.base.response_for = _v118_response
arch.base.response_for = _v118_response
'''

text += append
P.write_text(text)
print('applied arch-aware-v1.18-adversarial Kinnan colored-affordability repair')
