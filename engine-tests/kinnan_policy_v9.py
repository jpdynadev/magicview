#!/usr/bin/env python3
"""Kinnan policy v9 semantic capability registry and generic line families."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

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
    "copy_choice": Capability("copy_choice", True, "Copy choices are distinct from targets."),
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
