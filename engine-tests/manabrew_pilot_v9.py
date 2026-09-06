#!/usr/bin/env python3
"""Kinnan pilot v9 semantic adapter (alpha).

The v9 pilot deliberately does not fall back to v8 for ranking. It provides
architecture-neutral typed-action helpers for canaries while ranking remains
blocked until live Forge integration, anchor parity and telemetry v3 all pass.
"""
from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

import kinnan_policy_v9 as policy
from kinnan_semantics_v9 import CopyChoice, CopyKind, SelectionConstraint, SelectionKind, SemanticError, SemanticRoleProfile, architecture_neutral_role_score, priority_available

PILOT_VERSION = "v9.0.0-semantic-alpha"
POLICY_VERSION = policy.POLICY_VERSION
PRODUCTION_RANKING_READY = False
CANARY_ENV = "KINNAN_V9_ALLOW_CANARY"


def production_ranking_ready() -> bool:
    return bool(PRODUCTION_RANKING_READY)


def assert_ranking_ready() -> None:
    if not production_ranking_ready():
        raise RuntimeError("Kinnan pilot v9 semantic alpha is not production-ranking-ready; mechanic goldens, anchor parity, full-99 v3 and deterministic replay must pass first")


def _typed_card_meta(action: Mapping[str, Any]) -> dict[str, Any]:
    meta = dict(action.get("card") or action.get("cardInfo") or {})
    if "types" not in meta and action.get("cardTypes") is not None:
        meta["types"] = action.get("cardTypes")
    if "manaValue" not in meta and action.get("manaValue") is not None:
        meta["manaValue"] = action.get("manaValue")
    abilities = list(meta.get("abilities") or [])
    action_ability = {"kind": action.get("semanticKind") or action.get("abilityKind") or action.get("type"), "isManaAbility": bool(action.get("isManaAbility")), "producedMana": action.get("producedMana")}
    if any(v not in (None, False, "") for v in action_ability.values()):
        abilities.append(action_ability)
    meta["abilities"] = abilities
    meta["semanticTags"] = list(meta.get("semanticTags") or action.get("semanticTags") or [])
    return meta


def semantic_action_score(action: Mapping[str, Any], snapshot: Mapping[str, Any], *, player_id: str, horizon_turn: int = 4) -> float:
    if not priority_available(phase=str(snapshot.get("phase") or ""), step=str(snapshot.get("step") or ""), engine_priority_holder=snapshot.get("priorityPlayerId") or snapshot.get("priorityHolder")):
        return float("-inf")
    score = architecture_neutral_role_score(SemanticRoleProfile.from_typed_metadata(_typed_card_meta(action)), horizon_turn=horizon_turn)
    atype = str(action.get("type") or "").lower()
    step = str(snapshot.get("step") or snapshot.get("phase") or "").lower()
    if atype in {"pass", "passpriority"}:
        score -= 0.25
    elif atype in {"undomana", "undo_mana"}:
        # Forge exposes undoMana as a reversible UI affordance, not a forward
        # pilot decision. Never consume a typed-action budget by selecting it.
        score -= 100.0
    elif atype in {"playland", "play_land"}:
        score += 1.0
    elif atype in {"activateability", "activate_ability"} and action.get("isManaAbility"):
        # Floating mana in upkeep/combat/end step without a witnessed response
        # window only strands the resource before the next main phase.
        score += 0.5 if step in {"main1", "main2"} else -4.0
    elif atype in {"castspell", "cast_spell", "cast"}:
        score += 0.35
    if action.get("lineWitnessId"): score += 10.0
    if action.get("resolvesThreatToLineId"): score += 8.0
    planning_state = policy.planning_state_from_mapping(snapshot.get("planningContext"))
    if planning_state is not None:
        assessment = policy.assess_plan_action(action, planning_state)
        if assessment is not None:
            score += assessment.score_adjustment
    return score


def choose_action(actions: Sequence[Mapping[str, Any]], snapshot: Mapping[str, Any], *, player_id: str, horizon_turn: int = 4) -> Mapping[str, Any] | None:
    if not actions:
        return None
    stable = [a for a in actions if a.get("actionId") or a.get("id")]
    if not stable:
        raise SemanticError("typed action identity missing for every legal action")
    ranked = sorted(
        stable,
        key=lambda a: (
            semantic_action_score(
                a,
                snapshot,
                player_id=player_id,
                horizon_turn=horizon_turn,
            ),
            str(a.get("actionId") or a.get("id")),
        ),
        reverse=True,
    )
    best = ranked[0]
    # The protocol's pass action is implicit in live chooseAction prompts.
    # Return None when every explicit action is worse than passing.
    if semantic_action_score(
        best,
        snapshot,
        player_id=player_id,
        horizon_turn=horizon_turn,
    ) <= -0.25:
        return None
    return best


def classify_selection_prompt(prompt: Mapping[str, Any]) -> SelectionKind:
    inp = prompt.get("input") or {}
    explicit = str(inp.get("selectionKind") or prompt.get("selectionKind") or prompt.get("promptType") or prompt.get("type") or "").lower()
    if "copy" in explicit or inp.get("copySourceId") is not None: return SelectionKind.COPY
    if "search" in explicit or inp.get("searchZone") in {"library", "graveyard", "exile"}: return SelectionKind.SEARCH
    if "reveal" in explicit: return SelectionKind.REVEAL
    if "target" in explicit or inp.get("targeting") is True: return SelectionKind.TARGET
    return SelectionKind.CHOOSE


def choose_cards(prompt: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], *, desired_roles: Sequence[str] = ()) -> list[Mapping[str, Any]]:
    inp = prompt.get("input") or {}; kind = classify_selection_prompt(prompt)
    minimum = int(inp.get("min") or inp.get("minCount") or 0); maximum = int(inp.get("max") or inp.get("maxCount") or max(minimum, 1)); exact_mv = inp.get("exactManaValue")
    constraint = SelectionConstraint(kind=kind, min_count=minimum, max_count=maximum, allowed_card_ids=frozenset(str(c.get("id") or c.get("cardId")) for c in candidates if c.get("id") or c.get("cardId")), required_types=frozenset(str(x) for x in (inp.get("requiredTypes") or [])), exact_mana_value=int(exact_mv) if exact_mv is not None else None, may_fail_to_find=bool(inp.get("mayFailToFind", False)))
    wanted = {str(x).lower() for x in desired_roles}; scored = []
    for card in candidates:
        profile = SemanticRoleProfile.from_typed_metadata(card); tags = {str(x).lower() for x in card.get("semanticTags", [])}
        score = architecture_neutral_role_score(profile) + 3.0 * len(wanted & tags); cid = str(card.get("id") or card.get("cardId") or "")
        scored.append((score, cid, card))
    scored.sort(reverse=True, key=lambda x: (x[0], x[1])); selected = [x[2] for x in scored[:maximum]]
    if len(selected) < minimum or not constraint.validate(selected):
        if constraint.may_fail_to_find and minimum == 0: return []
        raise SemanticError(f"cannot make legal {kind.value} selection from typed candidates")
    return selected


def _selection_card_keep_score(
    card: Mapping[str, Any],
    *,
    horizon_turn: int = 4,
) -> float:
    """Score live typed card metadata for retention in hand.

    This stays architecture-neutral: it uses typed roles, mana value, and
    rules-text capabilities instead of a card-name allowlist.
    """
    meta = dict(card)
    if meta.get("manaValue") is None and meta.get("cmc") is not None:
        meta["manaValue"] = int(meta["cmc"])
    text = str(meta.get("text") or "").lower()
    tags = {str(tag).lower() for tag in meta.get("semanticTags", [])}
    if "add " in text and "mana" in text:
        tags.add("mana_source")
    if "search your library" in text:
        tags.add("tutor")
    if "counter target" in text or "destroy target" in text or "return target" in text:
        tags.add("interaction")
    if "hexproof" in text:
        tags.add("protection")
    if "draw " in text:
        tags.add("card_advantage")
    if "untap" in text:
        tags.add("untapper")
    if "copy " in text:
        tags.add("copy_effect")
    meta["semanticTags"] = sorted(tags)
    score = architecture_neutral_role_score(
        SemanticRoleProfile.from_typed_metadata(meta),
        horizon_turn=horizon_turn,
    )
    # Typed engine/connectivity effects not represented in the alpha role
    # profile still deserve retention credit.
    if "put any number of creature cards from your hand onto the battlefield" in text:
        score += 1.5
    if "have haste" in text or "as though" in text and "had haste" in text:
        score += 1.0
    return score


def choose_discard(
    candidates: Sequence[Mapping[str, Any]],
    *,
    count: int,
    horizon_turn: int = 4,
) -> list[Mapping[str, Any]]:
    """Choose the lowest keep-value cards for a mandatory discard."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise SemanticError("discard count must be a non-negative integer")
    stable = [
        card
        for card in candidates
        if card.get("id") or card.get("cardId")
    ]
    ids = [str(card.get("id") or card.get("cardId")) for card in stable]
    if len(stable) != len(candidates) or len(set(ids)) != len(ids):
        raise SemanticError("discard candidates require unique stable card identities")
    if count > len(stable):
        raise SemanticError("discard count exceeds typed candidates")
    return sorted(
        stable,
        key=lambda card: (
            _selection_card_keep_score(card, horizon_turn=horizon_turn),
            str(card.get("id") or card.get("cardId")),
        ),
    )[:count]


def choose_cost_permanents(
    candidates: Sequence[Mapping[str, Any]],
    *,
    count: int,
    horizon_turn: int = 4,
) -> list[Mapping[str, Any]]:
    """Spend the lowest typed opportunity-cost permanents from a legal set."""
    return choose_discard(candidates, count=count, horizon_turn=horizon_turn)


def _copy_kind(value: Any) -> CopyKind:
    folded = str(value or "permanent").replace("_", "").replace("-", "").casefold()
    aliases = {
        "permanent": CopyKind.PERMANENT,
        "spell": CopyKind.SPELL,
        "activatedability": CopyKind.ACTIVATED_ABILITY,
        "triggeredability": CopyKind.TRIGGERED_ABILITY,
    }
    if folded not in aliases:
        raise SemanticError(f"unsupported typed copy kind {value!r}")
    return aliases[folded]


def record_copy_choice(
    *,
    source_card_id: str,
    copied_object_id: str,
    copy_kind: str | CopyKind = CopyKind.PERMANENT,
    as_enters: bool | None = None,
    target_object_id: str | None = None,
    original_target_ids: Sequence[str] = (),
    chosen_target_ids: Sequence[str] = (),
    may_choose_new_targets: bool = False,
    original_x_value: int | None = None,
    copied_x_value: int | None = None,
) -> dict[str, Any]:
    kind = copy_kind if isinstance(copy_kind, CopyKind) else _copy_kind(copy_kind)
    choice = CopyChoice(
        source_card_id=source_card_id,
        copied_object_id=copied_object_id,
        copy_kind=kind,
        as_enters=kind == CopyKind.PERMANENT if as_enters is None else as_enters,
        target_object_id=target_object_id,
        original_target_ids=tuple(str(x) for x in original_target_ids),
        chosen_target_ids=tuple(str(x) for x in chosen_target_ids),
        may_choose_new_targets=may_choose_new_targets,
        original_x_value=original_x_value,
        copied_x_value=copied_x_value,
    )
    result = choice.__dict__.copy()
    result["copy_kind"] = choice.copy_kind.value
    result["effective_target_ids"] = choice.effective_target_ids
    result["effective_x_value"] = choice.effective_x_value
    return result


def choose_copy_object(
    prompt: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_card_id: str,
    desired_roles: Sequence[str] = (),
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Choose one engine-authorized object and emit an auditable copy witness."""
    inp = prompt.get("input") or prompt
    if not candidates:
        raise SemanticError("copy prompt has no engine-authorized candidates")
    copy_prompt = {"input": {**inp, "selectionKind": "copy", "min": 1, "max": 1}}
    chosen = choose_cards(copy_prompt, candidates, desired_roles=desired_roles)
    if len(chosen) != 1:
        raise SemanticError("copy prompt must resolve to exactly one object")
    copied = chosen[0]
    copied_id = str(copied.get("id") or copied.get("cardId") or "")
    raw_kind = inp.get("copyKind") or copied.get("copyKind") or copied.get("objectKind")
    if raw_kind is None and (inp.get("asEnters") is True or str(copied.get("zone") or "").casefold() == "battlefield"):
        raw_kind = "permanent"
    if raw_kind is None:
        raise SemanticError("copy candidate requires typed permanent, spell, or ability kind")
    kind = _copy_kind(raw_kind)
    original_targets = tuple(str(x) for x in (inp.get("originalTargetIds") or copied.get("targetIds") or ()))
    copied_x = inp.get("originalXValue", copied.get("xValue"))
    typed_as_enters = inp.get("asEnters")
    witness = record_copy_choice(
        source_card_id=source_card_id,
        copied_object_id=copied_id,
        copy_kind=kind,
        as_enters=typed_as_enters if isinstance(typed_as_enters, bool) else None,
        target_object_id=str(inp.get("targetObjectId")) if inp.get("targetObjectId") else None,
        original_target_ids=original_targets,
        original_x_value=copied_x,
    )
    return copied, witness


def canary_main() -> int:
    if os.getenv(CANARY_ENV) != "1": assert_ranking_ready()
    snapshot = {"phase": "main1", "step": "main1", "priorityPlayerId": "player-0"}
    actions = [{"actionId": "a1", "type": "castSpell", "cardTypes": ["Creature"], "manaValue": 2, "semanticTags": ["mana_source"], "abilities": [{"kind": "mana", "isManaAbility": True, "producedMana": {"G": 1}}]}, {"actionId": "a2", "type": "pass"}]
    chosen = choose_action(actions, snapshot, player_id="player-0")
    print(json.dumps({"pilotVersion": PILOT_VERSION, "policyVersion": POLICY_VERSION, "productionRankingReady": production_ranking_ready(), "canaryChosenActionId": chosen.get("actionId") if chosen else None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(canary_main())
