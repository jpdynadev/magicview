#!/usr/bin/env python3
"""Kinnan policy v9 semantic capability registry and generic line families."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping, Sequence

from kinnan_semantics_v9 import LineWitness, ResourceDelta, ResourceTransform, SemanticRoleProfile, architecture_neutral_role_score, prove_repeatable_cycle

POLICY_VERSION = "kinnan-policy-v9.0.0-alpha"


@dataclass(frozen=True)
class Capability:
    capability_id: str
    critical: bool
    description: str
    required_semantic_fields: tuple[str, ...] = ()


CAPABILITIES: dict[str, Capability] = {
    "typed_action_identity": Capability("typed_action_identity", True, "Stable typed action/card/ability/object identities.", ("actionId", "cardId")),
    "typed_mana_ledger": Capability("typed_mana_ledger", True, "Source-aware mana production and exact payment attribution.", ("actionId", "cardId", "abilityId")),
    "convoke_payment": Capability("convoke_payment", True, "Convoke is payment, never mana production."),
    "creature_mana": Capability("creature_mana", True, "Creature mana uses typed mana-ability metadata."),
    "copy_choice": Capability("copy_choice", True, "Permanent, spell and ability copies preserve typed object identity, targets and X; as-enters copy choices are not targets.", ("copyKind", "copiedObjectId")),
    "search_selection": Capability("search_selection", True, "Search/reveal/target/copy selections are distinct."),
    "vannifar_chain": Capability("vannifar_chain", True, "Prime Speaker Vannifar searches exactly MV+1 creatures."),
    "soulbond_blink": Capability("soulbond_blink", True, "Blink creates a new object and breaks/reforms soulbond."),
    "seedborn_priority": Capability("seedborn_priority", True, "Opponent-turn state persists; no actions without priority."),
    "generic_resource_cycle": Capability("generic_resource_cycle", True, "Repeatable loops require a proved legal resource cycle."),
    "pili_pala_cycle": Capability("pili_pala_cycle", True, "Pili-family loops derive from resource transforms, not card co-presence."),
    "knacksaw_cycle": Capability("knacksaw_cycle", True, "Knacksaw exile/play permissions must be represented explicitly."),
    "deadeye_cycle": Capability("deadeye_cycle", True, "Deadeye loops require soulbond lifecycle, blink identity and a resource-positive ETB cycle."),
    "freed_pemmins_cycle": Capability("freed_pemmins_cycle", True, "Aura untap loops require a resource-positive source/untap cycle."),
    "monolith_cycle": Capability("monolith_cycle", True, "Existing Monolith lines use the same generic resource proof."),
    "resolved_stack_protection": Capability("resolved_stack_protection", True, "Protection credit requires explicit interaction, response and resolution."),
    "full99_v3": Capability("full99_v3", True, "Every valid game requires 99 registered per-card telemetry rows."),
    "role_symmetry": Capability("role_symmetry", True, "Equivalent typed semantic roles score equivalently independent of card name."),
}


@dataclass(frozen=True)
class PlanCandidate:
    plan_id: str
    roles: tuple[str, ...]
    score: float
    witness: LineWitness | None = None


MAX_PLAN_BRANCHES = 32
MAX_PLAN_ROLES = 16


@dataclass(frozen=True)
class PlanBranch:
    """A typed, architecture-neutral route through a non-linear win plan.

    ``required_roles`` describes the pieces the route ultimately needs, while
    ``ordered_roles`` describes only the portion whose order matters.  Tutors
    remain actions rather than virtual combo pieces: a tutor advances a branch
    only when its typed ``searchableRoles`` can find a currently missing role.
    """

    plan_id: str
    required_roles: frozenset[str]
    ordered_roles: tuple[str, ...] = ()
    priority: float = 0.0
    fallback: bool = False
    blocked: bool = False
    loop_witness_id: str | None = None


@dataclass(frozen=True)
class PlanningState:
    available_roles: frozenset[str]
    branches: tuple[PlanBranch, ...]
    witnessed_line_ids: frozenset[str] = frozenset()
    threatened_line_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PlanAssessment:
    plan_id: str
    score_adjustment: float
    advanced_roles: tuple[str, ...]
    missing_roles: tuple[str, ...]
    completes_route: bool
    protects_route: bool


def _role_set(value: Any, *, field_name: str) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{field_name} must be a role sequence")
    roles = tuple(str(role).strip().lower() for role in value)
    if any(not role for role in roles) or len(roles) > MAX_PLAN_ROLES:
        raise ValueError(f"{field_name} contains invalid or excessive roles")
    return frozenset(roles)


def _id_set(value: Any, *, field_name: str) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{field_name} must be an identity sequence")
    identities = tuple(str(identity).strip() for identity in value)
    if any(not identity for identity in identities) or len(identities) > MAX_PLAN_BRANCHES:
        raise ValueError(f"{field_name} contains invalid or excessive identities")
    return frozenset(identities)


def planning_state_from_mapping(value: Mapping[str, Any] | None) -> PlanningState | None:
    """Parse an optional live planning context, failing closed when malformed."""

    if value is None:
        return None
    raw_branches = value.get("branches") or []
    if not isinstance(raw_branches, list) or len(raw_branches) > MAX_PLAN_BRANCHES:
        raise ValueError("planning branches must be a bounded list")
    branches: list[PlanBranch] = []
    plan_ids: set[str] = set()
    for raw in raw_branches:
        if not isinstance(raw, Mapping):
            raise ValueError("planning branch must be an object")
        plan_id = str(raw.get("planId") or "").strip()
        if not plan_id:
            raise ValueError("planning branch requires planId")
        if plan_id in plan_ids:
            raise ValueError(f"duplicate planning branch {plan_id}")
        plan_ids.add(plan_id)
        ordered = tuple(str(role).strip().lower() for role in (raw.get("orderedRoles") or ()))
        if any(not role for role in ordered) or len(ordered) > MAX_PLAN_ROLES:
            raise ValueError("orderedRoles contains invalid or excessive roles")
        required = _role_set(raw.get("requiredRoles"), field_name="requiredRoles") | frozenset(ordered)
        if not required or len(required) > MAX_PLAN_ROLES:
            raise ValueError("planning branch requires at least one semantic role")
        priority = float(raw.get("priority") or 0.0)
        if not math.isfinite(priority) or abs(priority) > 100.0:
            raise ValueError("planning branch priority must be finite and bounded")
        branches.append(PlanBranch(
            plan_id=plan_id,
            required_roles=required,
            ordered_roles=ordered,
            priority=priority,
            fallback=bool(raw.get("fallback", False)),
            blocked=bool(raw.get("blocked", False)),
            loop_witness_id=str(raw["loopWitnessId"]) if raw.get("loopWitnessId") else None,
        ))
    return PlanningState(
        available_roles=_role_set(value.get("availableRoles"), field_name="availableRoles"),
        branches=tuple(branches),
        witnessed_line_ids=_id_set(value.get("witnessedLineIds"), field_name="witnessedLineIds"),
        threatened_line_ids=_id_set(value.get("threatenedLineIds"), field_name="threatenedLineIds"),
    )


def assess_plan_action(action: Mapping[str, Any], state: PlanningState) -> PlanAssessment | None:
    """Score one legal action against all viable branches without lookahead.

    The search is deliberately bounded to the current legal action set and the
    declared branches.  It never invents a tutor target, loop witness, future
    draw, or protection event that the engine has not exposed.
    """

    action_roles = (
        _role_set(action.get("semanticTags"), field_name="semanticTags")
        | _role_set(action.get("providesRoles"), field_name="providesRoles")
    )
    searchable_roles = _role_set(action.get("searchableRoles"), field_name="searchableRoles")
    is_tutor = "tutor" in action_roles or "search" in action_roles
    resolves = str(action.get("resolvesThreatToLineId") or action.get("protectsLineId") or "")

    primary_viable = any(not branch.blocked and not branch.fallback for branch in state.branches)
    assessments: list[PlanAssessment] = []
    for branch in state.branches:
        if branch.blocked or (branch.fallback and primary_viable):
            continue
        missing_before = branch.required_roles - state.available_roles
        direct = action_roles & missing_before
        tutored = searchable_roles & missing_before if is_tutor else frozenset()
        advanced = direct | tutored

        next_ordered = next(
            (role for role in branch.ordered_roles if role not in state.available_roles),
            None,
        )
        out_of_order = bool(
            next_ordered
            and (action_roles & frozenset(branch.ordered_roles))
            and next_ordered not in advanced
        )
        protects = branch.plan_id in state.threatened_line_ids and resolves == branch.plan_id
        remaining = missing_before - advanced
        witness_ready = (
            branch.loop_witness_id is None
            or branch.loop_witness_id in state.witnessed_line_ids
            or str(action.get("lineWitnessId") or "") == branch.loop_witness_id
        )
        supplies_witness = bool(
            branch.loop_witness_id
            and str(action.get("lineWitnessId") or "") == branch.loop_witness_id
            and branch.loop_witness_id not in state.witnessed_line_ids
        )
        completes = not remaining and witness_ready and bool(advanced or supplies_witness)

        adjustment = branch.priority
        adjustment += 5.0 * len(direct) + 3.5 * len(tutored - direct)
        if next_ordered and next_ordered in advanced:
            adjustment += 3.0
        if out_of_order:
            adjustment -= 6.0
        if not remaining and not witness_ready:
            # Co-presence is not proof of a repeatable line.
            adjustment -= 8.0
        if completes:
            adjustment += 12.0
        if branch.plan_id in state.threatened_line_ids:
            adjustment += 20.0 if protects else -5.0
        if branch.fallback:
            adjustment -= 1.0
        if advanced or protects or completes:
            assessments.append(PlanAssessment(
                plan_id=branch.plan_id,
                score_adjustment=adjustment,
                advanced_roles=tuple(sorted(advanced)),
                missing_roles=tuple(sorted(remaining)),
                completes_route=completes,
                protects_route=protects,
            ))
    if not assessments:
        return None
    return max(assessments, key=lambda item: (item.score_adjustment, item.plan_id))


def score_card_metadata(meta: dict, *, horizon_turn: int = 4) -> float:
    return architecture_neutral_role_score(SemanticRoleProfile.from_typed_metadata(meta), horizon_turn=horizon_turn)


def prove_tap_untap_loop(*, line_id: str, produced_mana: int, untap_cost: int, available_roles: Iterable[str], producer_role: str, untapper_role: str, outlet_role: str | None, essential_card_ids: Sequence[str]) -> LineWitness | None:
    if produced_mana <= 0 or untap_cost < 0:
        return None
    transforms = [
        ResourceTransform("tap-for-mana", ResourceDelta(tapped_ready_resources=1), ResourceDelta(mana=produced_mana), frozenset({producer_role})),
        ResourceTransform("pay-to-untap", ResourceDelta(mana=untap_cost), ResourceDelta(tapped_ready_resources=1), frozenset({untapper_role})),
    ]
    return prove_repeatable_cycle(line_id, transforms, available_roles=available_roles, outlet_role=outlet_role, essential_card_ids=essential_card_ids)


def prove_pili_family(*, produced_mana: int, untap_cost: int, available_roles: Iterable[str], outlet_role: str | None, essential_card_ids: Sequence[str]) -> LineWitness | None:
    return prove_tap_untap_loop(line_id="PILI_PALA_FAMILY", produced_mana=produced_mana, untap_cost=untap_cost, available_roles=available_roles, producer_role="pili_mana_engine", untapper_role="pili_untap_engine", outlet_role=outlet_role, essential_card_ids=essential_card_ids)


def prove_freed_family(*, source_mana: int, untap_cost: int, available_roles: Iterable[str], outlet_role: str | None, essential_card_ids: Sequence[str]) -> LineWitness | None:
    return prove_tap_untap_loop(line_id="AURA_UNTAP_FAMILY", produced_mana=source_mana, untap_cost=untap_cost, available_roles=available_roles, producer_role="enchanted_mana_source", untapper_role="aura_untapper", outlet_role=outlet_role, essential_card_ids=essential_card_ids)


def prove_monolith_family(*, produced_mana: int, untap_cost: int, available_roles: Iterable[str], outlet_role: str | None, essential_card_ids: Sequence[str]) -> LineWitness | None:
    return prove_tap_untap_loop(line_id="MONOLITH_FAMILY", produced_mana=produced_mana, untap_cost=untap_cost, available_roles=available_roles, producer_role="monolith_mana_engine", untapper_role="monolith_untap_engine", outlet_role=outlet_role, essential_card_ids=essential_card_ids)


def prove_deadeye_family(*, etb_mana_gain: int, blink_cost: int, available_roles: Iterable[str], outlet_role: str | None, essential_card_ids: Sequence[str]) -> LineWitness | None:
    """Pure resource proof. Live integration must additionally verify soulbond and new-object identity."""
    return prove_repeatable_cycle(
        "DEADEYE_ETB_BLINK_FAMILY",
        [ResourceTransform("pay-blink", ResourceDelta(mana=blink_cost), ResourceDelta(), frozenset({"soulbond_blink_engine"})), ResourceTransform("etb-untap-or-mana", ResourceDelta(), ResourceDelta(mana=etb_mana_gain), frozenset({"etb_resource_engine"}))],
        available_roles=available_roles,
        outlet_role=outlet_role,
        essential_card_ids=essential_card_ids,
    )


def prove_knacksaw_family(
    *,
    produced_mana: int,
    untap_cost: int,
    cards_exiled_per_cycle: int,
    available_roles: Iterable[str],
    essential_card_ids: Sequence[str],
) -> LineWitness | None:
    """Prove a repeatable library-exile cycle without inventing play permission."""

    if produced_mana <= 0 or untap_cost < 0 or cards_exiled_per_cycle <= 0:
        return None
    transforms = [
        ResourceTransform(
            "knacksaw-tap-for-mana",
            ResourceDelta(tapped_ready_resources=1),
            ResourceDelta(mana=produced_mana),
            frozenset({"knacksaw_mana_engine"}),
        ),
        ResourceTransform(
            "knacksaw-untap-exile",
            ResourceDelta(mana=untap_cost),
            ResourceDelta(
                tapped_ready_resources=1,
                opponent_library_exiled=cards_exiled_per_cycle,
            ),
            frozenset({"knacksaw_untap_engine"}),
        ),
    ]
    return prove_repeatable_cycle(
        "KNACKSAW_LIBRARY_EXILE_FAMILY",
        transforms,
        available_roles=available_roles,
        outlet_role="library_exile_outlet",
        essential_card_ids=essential_card_ids,
    )
