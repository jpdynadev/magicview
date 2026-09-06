#!/usr/bin/env python3
"""Strict transport boundary for queued Kinnan planning state."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Mapping

import kinnan_policy_v9 as policy
from kinnan_semantics_v9 import SemanticError

PLANNING_CONTEXT_ENV = "KINNAN_PLANNING_CONTEXT_JSON"
MAX_PLANNING_CONTEXT_BYTES = 32 * 1024
ROLE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
LINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
TOP_LEVEL_FIELDS = frozenset({
    "availableRoles", "branches", "witnessedLineIds", "threatenedLineIds",
})
BRANCH_FIELDS = frozenset({
    "planId", "requiredRoles", "orderedRoles", "priority", "fallback",
    "blocked", "loopWitnessId",
})


def _sequence(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise SemanticError(f"planningContext.{field} must be a JSON array")
    return value


def _roles(value: Any, field: str) -> list[str]:
    roles = _sequence(value, field)
    if len(roles) > policy.MAX_PLAN_ROLES:
        raise SemanticError(f"planningContext.{field} exceeds {policy.MAX_PLAN_ROLES} roles")
    if any(not isinstance(role, str) or not ROLE_ID_RE.fullmatch(role) for role in roles):
        raise SemanticError(f"planningContext.{field} contains an invalid role ID")
    if len(set(roles)) != len(roles):
        raise SemanticError(f"planningContext.{field} contains duplicate role IDs")
    return roles


def _line_ids(value: Any, field: str) -> list[str]:
    identities = _sequence(value, field)
    if len(identities) > policy.MAX_PLAN_BRANCHES:
        raise SemanticError(f"planningContext.{field} exceeds {policy.MAX_PLAN_BRANCHES} IDs")
    if any(not isinstance(item, str) or not LINE_ID_RE.fullmatch(item) for item in identities):
        raise SemanticError(f"planningContext.{field} contains an invalid line ID")
    if len(set(identities)) != len(identities):
        raise SemanticError(f"planningContext.{field} contains duplicate line IDs")
    return identities


def validate_planning_context(value: Any) -> dict[str, Any]:
    """Validate and canonicalize the only planning payload accepted at runtime."""
    if not isinstance(value, Mapping):
        raise SemanticError("planningContext must be a JSON object")
    unknown = set(value) - TOP_LEVEL_FIELDS
    if unknown:
        raise SemanticError(f"planningContext has unknown fields: {sorted(unknown)}")
    raw_size = len(json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    if raw_size > MAX_PLANNING_CONTEXT_BYTES:
        raise SemanticError(
            f"planningContext exceeds {MAX_PLANNING_CONTEXT_BYTES} encoded bytes"
        )
    available = _roles(value.get("availableRoles", []), "availableRoles")
    witnessed = _line_ids(value.get("witnessedLineIds", []), "witnessedLineIds")
    threatened = _line_ids(value.get("threatenedLineIds", []), "threatenedLineIds")
    raw_branches = _sequence(value.get("branches"), "branches")
    if not raw_branches or len(raw_branches) > policy.MAX_PLAN_BRANCHES:
        raise SemanticError(
            f"planningContext.branches must contain 1-{policy.MAX_PLAN_BRANCHES} branches"
        )
    branches: list[dict[str, Any]] = []
    plan_ids: set[str] = set()
    for index, raw in enumerate(raw_branches):
        if not isinstance(raw, Mapping):
            raise SemanticError(f"planningContext.branches[{index}] must be an object")
        unknown_branch = set(raw) - BRANCH_FIELDS
        if unknown_branch:
            raise SemanticError(
                f"planningContext.branches[{index}] has unknown fields: {sorted(unknown_branch)}"
            )
        plan_id = raw.get("planId")
        if not isinstance(plan_id, str) or not LINE_ID_RE.fullmatch(plan_id):
            raise SemanticError(f"planningContext.branches[{index}].planId is invalid")
        if plan_id in plan_ids:
            raise SemanticError(f"duplicate planning branch {plan_id}")
        plan_ids.add(plan_id)
        required = _roles(raw.get("requiredRoles", []), f"branches[{index}].requiredRoles")
        ordered = _roles(raw.get("orderedRoles", []), f"branches[{index}].orderedRoles")
        if not required and not ordered:
            raise SemanticError(f"planning branch {plan_id} requires semantic roles")
        if len(set(required) | set(ordered)) > policy.MAX_PLAN_ROLES:
            raise SemanticError(f"planning branch {plan_id} exceeds the role limit")
        priority = raw.get("priority", 0.0)
        if (
            not isinstance(priority, (int, float))
            or isinstance(priority, bool)
            or not math.isfinite(float(priority))
            or abs(float(priority)) > 100.0
        ):
            raise SemanticError(f"planning branch {plan_id} priority is invalid")
        for flag in ("fallback", "blocked"):
            if flag in raw and not isinstance(raw[flag], bool):
                raise SemanticError(f"planning branch {plan_id} {flag} must be boolean")
        loop_id = raw.get("loopWitnessId")
        if loop_id is not None and (
            not isinstance(loop_id, str) or not LINE_ID_RE.fullmatch(loop_id)
        ):
            raise SemanticError(f"planning branch {plan_id} loopWitnessId is invalid")
        branch = {
            "planId": plan_id,
            "requiredRoles": required,
            "orderedRoles": ordered,
            "priority": float(priority),
            "fallback": bool(raw.get("fallback", False)),
            "blocked": bool(raw.get("blocked", False)),
        }
        if loop_id is not None:
            branch["loopWitnessId"] = loop_id
        branches.append(branch)
    normalized = {
        "availableRoles": available,
        "witnessedLineIds": witnessed,
        "threatenedLineIds": threatened,
        "branches": branches,
    }
    # Exercise the scoring parser at the transport boundary as a final parity check.
    policy.planning_state_from_mapping(normalized)
    return normalized


def planning_context_json(value: Any) -> str:
    normalized = validate_planning_context(value)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_PLANNING_CONTEXT_BYTES:
        raise SemanticError(
            f"canonical planningContext exceeds {MAX_PLANNING_CONTEXT_BYTES} bytes"
        )
    return payload


def load_planning_context_file(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve(strict=True)
    if source.stat().st_size > MAX_PLANNING_CONTEXT_BYTES:
        raise SemanticError(
            f"planningContext file exceeds {MAX_PLANNING_CONTEXT_BYTES} bytes"
        )
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticError(f"invalid planningContext file: {exc}") from exc
    return validate_planning_context(value)


def load_planning_context_env() -> dict[str, Any] | None:
    raw = os.environ.get(PLANNING_CONTEXT_ENV)
    if raw is None:
        return None
    if len(raw.encode("utf-8")) > MAX_PLANNING_CONTEXT_BYTES:
        raise SemanticError("planningContext environment payload is oversized")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SemanticError(f"invalid planningContext environment JSON: {exc}") from exc
    return validate_planning_context(value)


def planning_context_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(planning_context_json(value).encode("utf-8")).hexdigest()
