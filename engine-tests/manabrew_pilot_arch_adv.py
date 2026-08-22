#!/usr/bin/env python3
"""Compose architecture-aware Kinnan policy with adversarial opponent policy."""
from __future__ import annotations

from typing import Any

import manabrew_pilot_v91_adversarial as adversarial  # installs pod/deck/keep/target policy first
import manabrew_pilot_arch as arch
import manabrew_pilot_v8 as runner

# Cache/pilot identity must follow the repaired architecture policy actually in
# use. v1.10 broke a pathological Forge Mockingbird replacement loop. v1.11
# additionally prevents selecting Kinnan's seven-mana activation when the
# authoritative snapshot mana pool plus currently advertised mana abilities
# cannot actually pay it. Forge can advertise the activation before payment is
# feasible; cancelling the subsequent payManaCost prompt can strand the engine.
runner.PILOT_VERSION = 'arch-aware-v1.11-adversarial'

_COLOR_ALIASES = {
    'W': 'W', 'WHITE': 'W',
    'U': 'U', 'BLUE': 'U',
    'B': 'B', 'BLACK': 'B',
    'R': 'R', 'RED': 'R',
    'G': 'G', 'GREEN': 'G',
    'C': 'C', 'COLORLESS': 'C',
}


def choose_payment_color_exact(inp: dict[str, Any], preferred: list[str]) -> str:
    """Choose canonically, but submit the exact token Manabrew advertised.

    The canonical ChooseColorInput schema exposes the legal strings as
    `validColors`. Older pilot code looked only for `availableColors`/`colors`,
    so flexible sources such as Fellwar Stone could fall back to U/Blue even
    when that color was not one of Forge's legal options. Preserve the exact
    offered token while consuming the matching canonical preferred color.
    """
    raw_available = [
        str(item)
        for item in (
            inp.get('validColors')
            or inp.get('availableColors')
            or inp.get('colors')
            or []
        )
    ]
    canonical = [
        (raw, _COLOR_ALIASES.get(raw.strip().upper(), raw.strip().upper()))
        for raw in raw_available
    ]
    for pref in list(preferred):
        wanted = _COLOR_ALIASES.get(str(pref).strip().upper(), str(pref).strip().upper())
        for raw, offered in canonical:
            if offered == wanted:
                preferred.remove(pref)
                return raw
    if raw_available:
        return raw_available[0]
    return preferred.pop(0) if preferred else 'U'


# The v8 runner and architecture overlay share this module object, so this fixes
# adversarial chooseColor responses without changing Forge legality or screen-mode
# policy that already passed the production gate.
arch.policy.choose_payment_color = choose_payment_color_exact
runner.policy.choose_payment_color = choose_payment_color_exact

# Importing the architecture overlay intentionally replaces base.action_score so
# Kinnan can understand architecture cards. Re-compose the scorer here so
# non-Kinnan seats retain v9.1's race/disruption priorities in confirmation pods.
def composed_action_score(
    deck: str, action: dict[str, Any], snapshot: dict[str, Any], player: int
) -> int:
    if deck == 'Kinnan':
        return arch.action_score(deck, action, snapshot, player)
    return adversarial.adversarial_score(deck, action, snapshot, player)


arch.base.action_score = composed_action_score

# Forge can re-advertise an optional replacement boolean without changing the
# visible state when the accepted `true` branch has no resolvable follow-up.
# The generic policy quite reasonably says yes to prompts containing "copy",
# which previously made Blue Farm's Mockingbird repeat the same prompt thousands
# of times, fill the JVM heap, and eventually close harness stdout. Preserve the
# first normal answer; only if the exact Mockingbird prompt repeats in the exact
# same visible state do we decline the replacement so Forge can continue.
_ARCH_ADV_RESPONSE = runner.base.response_for
_MOCKINGBIRD_BOOLEAN_STATES: set[tuple[int, str, str]] = set()


def _player_mana_pool_total(snapshot: dict[str, Any], player: int) -> int:
    """Read authoritative floating mana from GameViewDto.PlayerDto."""
    wanted = f'player-{player}'
    for item in snapshot.get('players', []) or []:
        if str(item.get('id') or '') != wanted:
            continue
        pool = item.get('manaPool') or {}
        total = 0
        for value in pool.values():
            try:
                total += max(0, int(value or 0))
            except (TypeError, ValueError):
                continue
        return total
    return 0


def _mana_action_capacity(action: dict[str, Any]) -> int:
    """Upper-bound mana from one advertised source activation.

    Multiple color choices for the same permanent are deduplicated by caller.
    If the protocol omits producedMana for a known mana ability (for example a
    Chrome Mox color choice), count it conservatively as one mana.
    """
    if not (
        action.get('isManaAbility')
        or action.get('type') == 'activateManaAbility'
    ):
        return 0
    produced = action.get('producedMana') or []
    amount = 0
    for item in produced:
        try:
            amount += max(0, int(item.get('amount') or 0))
        except (AttributeError, TypeError, ValueError):
            continue
    return amount or 1


def _available_mana_upper_bound(
    inp: dict[str, Any], snapshot: dict[str, Any], player: int
) -> int:
    """Floating pool plus maximum one-shot mana from each advertised source."""
    per_source: dict[str, int] = {}
    for action in inp.get('actions', []) or []:
        capacity = _mana_action_capacity(action)
        if capacity <= 0:
            continue
        source = str(action.get('cardId') or action.get('card_id') or action.get('id') or '')
        if not source:
            continue
        per_source[source] = max(per_source.get(source, 0), capacity)
    return _player_mana_pool_total(snapshot, player) + sum(per_source.values())


def _guard_unpayable_kinnan_activation(
    prompt: dict[str, Any],
    snapshot: dict[str, Any],
    deck: str,
    player: int,
    answer: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Avoid the exact activate-then-cancel path that can idle Forge.

    Forge's chooseAction prompt may advertise Kinnan's {5}{G}{U} activation even
    when the subsequent payManaCost prompt cannot be completed. The v1.10
    forensic seed 3430166 reproduced this deterministically: the pilot selected
    Kinnan, payment cancelled as unpayable, and the harness received no further
    semantic progress. Only filter that activation when even an optimistic total
    of floating mana plus one activation from each advertised mana source is <7.
    Every other action and all actual payment/color legality remain Forge-owned.
    """
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
    description = str(chosen.get('description') or chosen.get('label') or '')
    cost = str(chosen.get('cost') or '')
    if '{5}{G}{U}' not in (cost + description).replace(' ', ''):
        return answer
    if _available_mana_upper_bound(inp, snapshot, player) >= 7:
        return answer

    filtered_prompt = dict(prompt)
    filtered_input = dict(inp)
    filtered_input['actions'] = [
        action for action in (inp.get('actions') or [])
        if str(action.get('id') or '') != chosen_id
    ]
    filtered_prompt['input'] = filtered_input
    retry = _ARCH_ADV_RESPONSE(filtered_prompt, snapshot, deck, player)
    if retry is not None:
        return retry
    return {'type': 'chooseAction', 'output': {'type': 'pass', 'exhaustStack': False}}


def repaired_response(
    prompt: dict[str, Any], snapshot: dict[str, Any], deck: str, player: int
) -> dict[str, Any] | None:
    inp = prompt.get('input') or {}
    if inp.get('type') == 'chooseBoolean':
        title = str((inp.get('presentation') or {}).get('title') or '')
        if 'apply replacement effect of mockingbird?' in title.lower():
            key = (player, arch.policy.visible_state_hash(snapshot), title)
            if key in _MOCKINGBIRD_BOOLEAN_STATES:
                return {
                    'type': 'chooseBoolean',
                    'output': {'type': 'decision', 'value': False},
                }
            _MOCKINGBIRD_BOOLEAN_STATES.add(key)
    answer = _ARCH_ADV_RESPONSE(prompt, snapshot, deck, player)
    return _guard_unpayable_kinnan_activation(prompt, snapshot, deck, player, answer)


runner.base.response_for = repaired_response
arch.base.response_for = repaired_response

if __name__ == '__main__':
    raise SystemExit(runner.main())
