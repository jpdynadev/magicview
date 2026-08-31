#!/usr/bin/env python3
"""Architecture-neutral semantic primitives for Kinnan pilot v9.

Forge remains the legality authority. These helpers normalize typed Manabrew/Forge
state into auditable facts. They intentionally fail closed rather than guessing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence
import hashlib
import json
import re

MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")
SCHEMA_VERSION = "kinnan-semantic-v9-alpha1"
FULL99_SCHEMA_VERSION = "kinnan-full99-card-telemetry-v3"


class SemanticError(ValueError):
    pass


class SelectionKind(str, Enum):
    TARGET = "target"
    SEARCH = "search"
    REVEAL = "reveal"
    COPY = "copy"
    CHOOSE = "choose"


class PaymentKind(str, Enum):
    MANA = "mana"
    CONVOKE = "convoke"
    IMPROVISE = "improvise"
    COST_REDUCTION = "costReduction"
    ALTERNATE = "alternate"
    ADDITIONAL = "additional"


class OutcomeRole(str, Enum):
    ABSENT_NOT_SEEN = "absent/notSeen"
    MERELY_PRESENT = "merelyPresent"
    INVOLVED = "involved"
    ESSENTIAL = "essential"


@dataclass(frozen=True)
class ManaVector:
    generic: int = 0
    W: int = 0
    U: int = 0
    B: int = 0
    R: int = 0
    G: int = 0
    C: int = 0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or value < 0:
                raise SemanticError(f"invalid mana {name}={value!r}")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ManaVector":
        if not value:
            return cls()
        n = {str(k).upper(): int(v) for k, v in value.items()}
        return cls(generic=int(n.get("GENERIC", 0)), **{s: int(n.get(s, 0)) for s in MANA_SYMBOLS})

    @classmethod
    def parse_cost(cls, text: str | None) -> "ManaVector":
        if not text:
            return cls()
        generic = 0
        colors = {s: 0 for s in MANA_SYMBOLS}
        for token in re.findall(r"\{([^}]+)\}", text.upper()):
            if token.isdigit():
                generic += int(token)
            elif token in colors:
                colors[token] += 1
            else:
                raise SemanticError(f"ambiguous mana symbol {{{token}}}; require engine-normalized cost")
        return cls(generic=generic, **colors)

    def total(self) -> int:
        return self.generic + sum(getattr(self, s) for s in MANA_SYMBOLS)

    def colored_total(self) -> int:
        return sum(getattr(self, s) for s in MANA_SYMBOLS)

    def add(self, other: "ManaVector") -> "ManaVector":
        return ManaVector(**{k: getattr(self, k) + getattr(other, k) for k in asdict(self)})

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class ManaProductionEvent:
    action_id: str
    source_card_id: str
    ability_id: str
    produced: ManaVector
    kinnan_bonus: ManaVector = ManaVector()
    turn: int | None = None
    phase: str | None = None
    step: str | None = None


@dataclass(frozen=True)
class PaymentComponent:
    action_id: str
    source_card_id: str | None
    amount: ManaVector
    kind: PaymentKind
    consumer_action_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ManaLedger:
    """Source-aware mana/payment ledger. Convoke/improvise never produce mana."""
    productions: list[ManaProductionEvent] = field(default_factory=list)
    payments: list[PaymentComponent] = field(default_factory=list)

    def record_production(self, event: ManaProductionEvent) -> None:
        if event.produced.total() + event.kinnan_bonus.total() <= 0:
            raise SemanticError("mana production event must produce positive mana")
        self.productions.append(event)

    def record_payment(self, component: PaymentComponent) -> None:
        if component.amount.total() <= 0:
            raise SemanticError("payment component must pay a positive amount")
        self.payments.append(component)

    def mana_produced(self) -> ManaVector:
        total = ManaVector()
        for e in self.productions:
            total = total.add(e.produced).add(e.kinnan_bonus)
        return total

    def mana_spent(self) -> ManaVector:
        total = ManaVector()
        for p in self.payments:
            if p.kind == PaymentKind.MANA:
                total = total.add(p.amount)
        return total

    def nonmana_payment_units(self, consumer_action_id: str) -> int:
        return sum(p.amount.total() for p in self.payments if p.consumer_action_id == consumer_action_id and p.kind != PaymentKind.MANA)

    def validate_consumer(self, consumer_action_id: str, engine_paid_cost: ManaVector) -> dict[str, Any]:
        parts = [p for p in self.payments if p.consumer_action_id == consumer_action_id]
        mana_parts = [p for p in parts if p.kind == PaymentKind.MANA]
        nonmana_parts = [p for p in parts if p.kind != PaymentKind.MANA]
        paid = ManaVector()
        for p in mana_parts:
            paid = paid.add(p.amount)
        deficits: dict[str, int] = {}
        for symbol in MANA_SYMBOLS:
            need = getattr(engine_paid_cost, symbol)
            have = getattr(paid, symbol)
            if have < need:
                deficits[symbol] = need - have
        generic_covered = max(0, paid.total() - engine_paid_cost.colored_total()) + sum(p.amount.total() for p in nonmana_parts)
        if generic_covered < engine_paid_cost.generic:
            deficits["generic"] = engine_paid_cost.generic - generic_covered
        return {
            "consumerActionId": consumer_action_id,
            "valid": not deficits,
            "enginePaidCost": engine_paid_cost.to_dict(),
            "actualManaPaid": paid.to_dict(),
            "substitutionUnits": sum(p.amount.total() for p in nonmana_parts),
            "deficits": deficits,
            "components": [{"kind": p.kind.value, "sourceCardId": p.source_card_id, "amount": p.amount.to_dict()} for p in parts],
        }


@dataclass(frozen=True)
class SelectionConstraint:
    kind: SelectionKind
    min_count: int = 1
    max_count: int = 1
    allowed_card_ids: frozenset[str] = frozenset()
    required_types: frozenset[str] = frozenset()
    exact_mana_value: int | None = None
    may_fail_to_find: bool = False

    def validate(self, selected: Sequence[Mapping[str, Any]]) -> bool:
        if not (self.min_count <= len(selected) <= self.max_count):
            return False
        for card in selected:
            cid = str(card.get("id") or card.get("cardId") or "")
            if self.allowed_card_ids and cid not in self.allowed_card_ids:
                return False
            types = {str(x).lower() for x in card.get("types", [])}
            if self.required_types and not {x.lower() for x in self.required_types}.issubset(types):
                return False
            if self.exact_mana_value is not None and int(card.get("manaValue", -1)) != self.exact_mana_value:
                return False
        return True


@dataclass(frozen=True)
class CopyChoice:
    source_card_id: str
    copied_object_id: str
    as_enters: bool = True
    target_object_id: str | None = None

    def __post_init__(self) -> None:
        if self.as_enters and self.target_object_id is not None:
            raise SemanticError("as-enters copy choice must not be recorded as a target")


def vannifar_candidates(sacrificed_mana_value: int, library: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    wanted = sacrificed_mana_value + 1
    return [c for c in library if "creature" in {str(t).lower() for t in c.get("types", [])} and int(c.get("manaValue", -1)) == wanted]


@dataclass
class SoulbondState:
    pairs: dict[str, str] = field(default_factory=dict)

    def pair(self, a: str, b: str) -> None:
        if a == b:
            raise SemanticError("object cannot soulbond with itself")
        self.unpair(a); self.unpair(b)
        self.pairs[a] = b; self.pairs[b] = a

    def unpair(self, obj: str) -> None:
        other = self.pairs.pop(obj, None)
        if other is not None:
            self.pairs.pop(other, None)

    def blink(self, old_object_id: str, new_object_id: str) -> None:
        self.unpair(old_object_id)
        if old_object_id == new_object_id:
            raise SemanticError("blink must create a new object identity")

    def partner(self, obj: str) -> str | None:
        return self.pairs.get(obj)


def priority_available(*, phase: str | None, step: str | None, engine_priority_holder: str | None) -> bool:
    if engine_priority_holder is None:
        return False
    return (step or "").lower() not in {"untap", "cleanup-no-priority"}


@dataclass(frozen=True)
class StackObject:
    stack_id: str
    controller_id: str
    source_card_id: str
    action_type: str
    targets: tuple[str, ...] = ()
    threatens_line_id: str | None = None


@dataclass(frozen=True)
class ResolutionEvent:
    stack_id: str
    status: str
    by_stack_id: str | None = None


@dataclass
class ProtectionCausality:
    stack_objects: dict[str, StackObject] = field(default_factory=dict)
    resolutions: list[ResolutionEvent] = field(default_factory=list)
    response_to: dict[str, str] = field(default_factory=dict)

    def push(self, obj: StackObject, *, response_to: str | None = None) -> None:
        if obj.stack_id in self.stack_objects:
            raise SemanticError(f"duplicate stack object {obj.stack_id}")
        self.stack_objects[obj.stack_id] = obj
        if response_to is not None:
            self.response_to[obj.stack_id] = response_to

    def resolve(self, event: ResolutionEvent) -> None:
        if event.stack_id not in self.stack_objects or event.status not in {"resolved", "countered", "fizzled"}:
            raise SemanticError(f"invalid resolution event {event}")
        self.resolutions.append(event)

    def protected_line(self, line_id: str) -> dict[str, Any]:
        threats = [o for o in self.stack_objects.values() if o.threatens_line_id == line_id]
        if not threats:
            return {"lineId": line_id, "interactionAttempted": False, "reactivelyProtected": False, "attemptSurvivedInteraction": False, "protectionStackIds": [], "threatStackIds": []}
        res = {r.stack_id: r for r in self.resolutions}
        successful: list[str] = []
        neutralized: set[str] = set()
        threat_ids = {t.stack_id for t in threats}
        for response_id, threat_id in self.response_to.items():
            if threat_id not in threat_ids:
                continue
            rr, tr = res.get(response_id), res.get(threat_id)
            if rr and rr.status == "resolved" and tr and tr.status in {"countered", "fizzled"}:
                successful.append(response_id); neutralized.add(threat_id)
        return {
            "lineId": line_id,
            "interactionAttempted": True,
            "reactivelyProtected": bool(successful),
            "attemptSurvivedInteraction": len(neutralized) == len(threats),
            "protectionStackIds": successful,
            "threatStackIds": sorted(threat_ids),
        }


@dataclass(frozen=True)
class ResourceDelta:
    mana: int = 0
    tapped_ready_resources: int = 0
    cards: int = 0
    life: int = 0


@dataclass(frozen=True)
class ResourceTransform:
    transform_id: str
    cost: ResourceDelta
    gain: ResourceDelta
    required_roles: frozenset[str] = frozenset()
    interruption_window: bool = True

    def net(self) -> ResourceDelta:
        return ResourceDelta(mana=self.gain.mana-self.cost.mana, tapped_ready_resources=self.gain.tapped_ready_resources-self.cost.tapped_ready_resources, cards=self.gain.cards-self.cost.cards, life=self.gain.life-self.cost.life)


@dataclass(frozen=True)
class LineWitness:
    line_id: str
    transform_ids: tuple[str, ...]
    repeatable: bool
    net_per_cycle: ResourceDelta
    required_roles: tuple[str, ...]
    outlet_role: str | None
    essential_card_ids: tuple[str, ...] = ()
    involved_card_ids: tuple[str, ...] = ()


def prove_repeatable_cycle(line_id: str, transforms: Sequence[ResourceTransform], *, available_roles: Iterable[str], outlet_role: str | None = None, essential_card_ids: Sequence[str] = (), involved_card_ids: Sequence[str] = ()) -> LineWitness | None:
    roles = set(available_roles); required: set[str] = set(); net = ResourceDelta()
    for t in transforms:
        required |= set(t.required_roles); d = t.net()
        net = ResourceDelta(net.mana+d.mana, net.tapped_ready_resources+d.tapped_ready_resources, net.cards+d.cards, net.life+d.life)
    if not required.issubset(roles):
        return None
    nonnegative = all(getattr(net, k) >= 0 for k in ("mana", "tapped_ready_resources", "cards", "life"))
    productive = any(getattr(net, k) > 0 for k in ("mana", "cards", "life")) or (outlet_role is not None and outlet_role in roles)
    if not (nonnegative and productive):
        return None
    return LineWitness(line_id, tuple(t.transform_id for t in transforms), True, net, tuple(sorted(required)), outlet_role, tuple(essential_card_ids), tuple(involved_card_ids))


@dataclass(frozen=True)
class SemanticRoleProfile:
    is_land: bool = False
    is_creature: bool = False
    is_artifact: bool = False
    is_mana_source: bool = False
    is_mana_sink: bool = False
    is_tutor: bool = False
    is_copy_effect: bool = False
    is_interaction: bool = False
    is_protection: bool = False
    is_card_advantage: bool = False
    is_untapper: bool = False
    is_outlet: bool = False
    mana_value: int | None = None

    @classmethod
    def from_typed_metadata(cls, meta: Mapping[str, Any]) -> "SemanticRoleProfile":
        types = {str(x).lower() for x in meta.get("types", [])}
        abilities = meta.get("abilities", []) or []
        tags = {str(x).lower() for x in meta.get("semanticTags", [])}
        kinds = {str(a.get("kind", "")).lower() for a in abilities if isinstance(a, Mapping)}
        produces_mana = any(bool(a.get("isManaAbility")) or a.get("producedMana") for a in abilities if isinstance(a, Mapping))
        return cls(
            is_land="land" in types, is_creature="creature" in types, is_artifact="artifact" in types,
            is_mana_source=produces_mana or "mana_source" in tags, is_mana_sink="mana_sink" in tags,
            is_tutor=bool({"search", "tutor"} & (kinds | tags)), is_copy_effect="copy" in kinds or "copy_effect" in tags,
            is_interaction=bool({"counter", "remove", "bounce"} & (kinds | tags)), is_protection="protection" in tags,
            is_card_advantage=bool({"draw", "card_advantage"} & (kinds | tags)), is_untapper="untap" in kinds or "untapper" in tags,
            is_outlet="outlet" in tags, mana_value=int(meta["manaValue"]) if meta.get("manaValue") is not None else None,
        )


def architecture_neutral_role_score(profile: SemanticRoleProfile, *, horizon_turn: int = 4) -> float:
    score = 0.0
    score += 2.5 if profile.is_mana_source else 0.0
    score += 2.0 if profile.is_tutor else 0.0
    score += 2.0 if profile.is_interaction else 0.0
    score += 1.75 if profile.is_protection else 0.0
    score += 1.5 if profile.is_card_advantage else 0.0
    score += 1.25 if profile.is_untapper else 0.0
    score += 1.25 if profile.is_copy_effect else 0.0
    score += 1.0 if profile.is_outlet else 0.0
    if profile.mana_value is not None:
        score -= max(0, profile.mana_value - max(1, horizon_turn // 2)) * 0.35
    return score


def build_full99_rows(*, game_id: str, deck_hash: str, registered_cards: Sequence[Mapping[str, Any]], observed_by_card_id: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(registered_cards) != 99:
        raise SemanticError(f"registered deck must contain exactly 99 cards, got {len(registered_cards)}")
    ids = [str(c.get("registeredCardId") or c.get("id") or "") for c in registered_cards]
    if any(not x for x in ids) or len(set(ids)) != 99:
        raise SemanticError("registered cards require 99 non-empty unique identities")
    unknown = set(observed_by_card_id) - set(ids)
    if unknown:
        raise SemanticError(f"observed unknown registered cards: {sorted(unknown)}")
    rows = []
    for card in registered_cards:
        cid = str(card.get("registeredCardId") or card.get("id")); obs = dict(observed_by_card_id.get(cid, {}))
        seen, involved, essential = bool(obs.get("seen", False)), bool(obs.get("involved", False)), bool(obs.get("essential", False))
        role = OutcomeRole.ESSENTIAL if essential else OutcomeRole.INVOLVED if involved else OutcomeRole.MERELY_PRESENT if seen else OutcomeRole.ABSENT_NOT_SEEN
        rows.append({
            "schemaVersion": FULL99_SCHEMA_VERSION, "gameId": game_id, "deckHash": deck_hash, "registeredCardId": cid,
            "cardName": card.get("cardName") or card.get("name"), "seen": seen, "openingHand": bool(obs.get("openingHand", False)),
            "kept": bool(obs.get("kept", False)), "mulliganed": bool(obs.get("mulliganed", False)), "firstSeenTurn": obs.get("firstSeenTurn"),
            "firstDrawnTurn": obs.get("firstDrawnTurn"), "zoneChanges": list(obs.get("zoneChanges", [])), "tutored": bool(obs.get("tutored", False)),
            "revealed": bool(obs.get("revealed", False)), "cast": bool(obs.get("cast", False)), "played": bool(obs.get("played", False)),
            "manaProduced": dict(obs.get("manaProduced", {})), "manaSpent": int(obs.get("manaSpent", 0) or 0), "activated": bool(obs.get("activated", False)),
            "used": bool(obs.get("used", False)), "comboParticipation": bool(obs.get("comboParticipation", False)),
            "protectionParticipation": bool(obs.get("protectionParticipation", False)), "interactionParticipation": bool(obs.get("interactionParticipation", False)),
            "attemptPresent": bool(obs.get("attemptPresent", False)), "protectedAttemptPresent": bool(obs.get("protectedAttemptPresent", False)),
            "naturalWinPresence": bool(obs.get("naturalWinPresence", False)), "packageExecution": bool(obs.get("packageExecution", False)), "outcomeRole": role.value,
        })
    return rows


def validate_full99_coverage(rows: Sequence[Mapping[str, Any]], *, valid_game_ids: Sequence[str], registered_card_ids_by_game: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    expected_rows = len(valid_game_ids) * 99; missing: dict[str, list[str]] = {}; duplicates: dict[str, list[str]] = {}; unknown: dict[str, list[str]] = {}; distinct: dict[str, int] = {}
    grouped = {gid: [] for gid in valid_game_ids}
    for row in rows:
        gid = str(row.get("gameId"))
        if gid in grouped:
            grouped[gid].append(row)
    for gid in valid_game_ids:
        expected = list(map(str, registered_card_ids_by_game.get(gid, [])))
        if len(expected) != 99 or len(set(expected)) != 99:
            raise SemanticError(f"invalid registration for game {gid}: expected exactly 99 unique ids")
        actual = [str(r.get("registeredCardId")) for r in grouped.get(gid, [])]; distinct[gid] = len(set(actual)); counts: dict[str, int] = {}
        for cid in actual:
            counts[cid] = counts.get(cid, 0) + 1
        m = sorted(set(expected)-set(actual)); d = sorted(k for k,v in counts.items() if v > 1); u = sorted(set(actual)-set(expected))
        if m: missing[gid] = m
        if d: duplicates[gid] = d
        if u: unknown[gid] = u
    valid = len(rows) == expected_rows and not missing and not duplicates and not unknown and all(v == 99 for v in distinct.values())
    return {"schemaVersion": FULL99_SCHEMA_VERSION, "valid": valid, "validGames": len(valid_game_ids), "expectedRows": expected_rows, "actualRows": len(rows), "missingCards": missing, "duplicates": duplicates, "unknownCards": unknown, "distinctCardsByGame": distinct}


def stable_semantic_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
