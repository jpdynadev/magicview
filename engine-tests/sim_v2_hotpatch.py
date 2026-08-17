#!/usr/bin/env python3
"""Runtime optimizer for the proven v8 pilot.

This module rewrites only the hot run_game function in memory. Decision logic,
card scoring, RPC semantics and primary result fields remain the v8 implementation.
The transform is intentionally small and mechanically tested against cold seeded
execution:

* replace the per-game trace list with a sink unless audit tracing is enabled;
* stop immediately after a protected deterministic attempt inside the configured
  T4 horizon, because the primary endpoint is already decided positively;
* stop a negative game as soon as Kinnan's own turn in the final observed round
  has ended, rather than simulating later seats in that same pod round.

The optimized function is installed into the runner module only for the current
Python worker process. Source files for the validated legacy pilot are untouched.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any


class _TraceSink(list):
    """JSON-serializable list that discards appended trace rows."""

    def append(self, item: Any) -> None:  # noqa: ARG002
        return None

    def extend(self, items: Any) -> None:  # noqa: ARG002
        return None


class _RunGameTransform(ast.NodeTransformer):
    def __init__(self, *, early_success: bool, trace_enabled: bool, exact_deadline: bool) -> None:
        self.early_success = early_success
        self.trace_enabled = trace_enabled
        self.exact_deadline = exact_deadline
        self.trace_replaced = 0
        self.early_exit_inserted = 0
        self.deadline_exit_inserted = 0

    @staticmethod
    def _is_result_key(target: ast.AST, key: str) -> bool:
        return (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "result"
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == key
        )

    @staticmethod
    def _result_store(key: str, value: ast.expr) -> ast.Assign:
        return ast.Assign(
            targets=[
                ast.Subscript(
                    value=ast.Name(id="result", ctx=ast.Load()),
                    slice=ast.Constant(value=key),
                    ctx=ast.Store(),
                )
            ],
            value=value,
        )

    def _deadline_condition(self) -> ast.expr:
        # Global turn numbering is 1-based and round_from_global_turn is
        # ((turn-1)//4)+1. Kinnan seat S takes its final observed turn at:
        # ((max_round-1)*4 + S + 1). Once global_turn advances beyond that,
        # Kinnan cannot create a new T4 attempt, so later seats are irrelevant to
        # the strict protected-T4 endpoint.
        deadline = ast.BinOp(
            left=ast.BinOp(
                left=ast.BinOp(
                    left=ast.BinOp(
                        left=ast.Name(id="max_round", ctx=ast.Load()),
                        op=ast.Sub(),
                        right=ast.Constant(value=1),
                    ),
                    op=ast.Mult(),
                    right=ast.Constant(value=4),
                ),
                op=ast.Add(),
                right=ast.Name(id="kinnan_seat", ctx=ast.Load()),
            ),
            op=ast.Add(),
            right=ast.Constant(value=1),
        )
        current_turn = ast.Call(
            func=ast.Name(id="int", ctx=ast.Load()),
            args=[ast.BoolOp(op=ast.Or(), values=[ast.Name(id="global_turn", ctx=ast.Load()), ast.Constant(value=0)])],
            keywords=[],
        )
        return ast.BoolOp(
            op=ast.And(),
            values=[
                ast.Name(id="_V2_EXACT_DEADLINE", ctx=ast.Load()),
                ast.Compare(left=current_turn, ops=[ast.Gt()], comparators=[deadline]),
            ],
        )

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self.generic_visit(node)
        if isinstance(node.target, ast.Name) and node.target.id == "trace" and not self.trace_enabled:
            node.value = ast.Call(func=ast.Name(id="_V2_TRACE_SINK", ctx=ast.Load()), args=[], keywords=[])
            self.trace_replaced += 1
        return node

    def visit_Assign(self, node: ast.Assign):
        self.generic_visit(node)
        if not self.trace_enabled:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "trace":
                    node.value = ast.Call(func=ast.Name(id="_V2_TRACE_SINK", ctx=ast.Load()), args=[], keywords=[])
                    self.trace_replaced += 1
                    break

        # Insert the negative endpoint stop immediately after the legacy runner
        # updates result['round']. There are two such sites: normal prompt
        # progress and repeated-prompt snapshot polling. Both live in the same
        # game loop and can safely break it.
        if self.exact_deadline and any(self._is_result_key(t, "round") for t in node.targets):
            body = [
                self._result_store("status", ast.Constant(value="horizon_complete")),
                self._result_store("v2DeadlineExit", ast.Constant(value=True)),
                ast.Break(),
            ]
            self.deadline_exit_inserted += 1
            return [node, ast.If(test=self._deadline_condition(), body=body, orelse=[])]

        if self.early_success and any(
            self._is_result_key(target, "protectedAttempt") for target in node.targets
        ):
            # At this point the legacy runner has already recognized a
            # deterministic combo line, classified the attempted action, set
            # firstAttemptTurn, and calculated whether protection is available.
            # If both assembly and attempt happened inside the observation
            # horizon, the strict protected-T4 endpoint cannot become false
            # later. Stop before spending prompts resolving the rest of a game
            # whose primary metric is already known.
            condition = ast.BoolOp(
                op=ast.And(),
                values=[
                    ast.Name(id="_V2_EARLY_SUCCESS", ctx=ast.Load()),
                    ast.Call(
                        func=ast.Name(id="bool", ctx=ast.Load()),
                        args=[
                            ast.Subscript(
                                value=ast.Name(id="result", ctx=ast.Load()),
                                slice=ast.Constant(value="protectedAttempt"),
                                ctx=ast.Load(),
                            )
                        ],
                        keywords=[],
                    ),
                    ast.Compare(
                        left=ast.Subscript(
                            value=ast.Name(id="result", ctx=ast.Load()),
                            slice=ast.Constant(value="firstAttemptTurn"),
                            ctx=ast.Load(),
                        ),
                        ops=[ast.IsNot()],
                        comparators=[ast.Constant(value=None)],
                    ),
                    ast.Compare(
                        left=ast.Subscript(
                            value=ast.Name(id="result", ctx=ast.Load()),
                            slice=ast.Constant(value="firstAttemptTurn"),
                            ctx=ast.Load(),
                        ),
                        ops=[ast.LtE()],
                        comparators=[ast.Name(id="max_round", ctx=ast.Load())],
                    ),
                    ast.Compare(
                        left=ast.Subscript(
                            value=ast.Name(id="result", ctx=ast.Load()),
                            slice=ast.Constant(value="firstAssemblyTurn"),
                            ctx=ast.Load(),
                        ),
                        ops=[ast.IsNot()],
                        comparators=[ast.Constant(value=None)],
                    ),
                    ast.Compare(
                        left=ast.Subscript(
                            value=ast.Name(id="result", ctx=ast.Load()),
                            slice=ast.Constant(value="firstAssemblyTurn"),
                            ctx=ast.Load(),
                        ),
                        ops=[ast.LtE()],
                        comparators=[ast.Name(id="max_round", ctx=ast.Load())],
                    ),
                ],
            )
            body = [
                self._result_store("status", ast.Constant(value="horizon_complete")),
                self._result_store("v2EarlyExit", ast.Constant(value=True)),
                ast.Break(),
            ]
            self.early_exit_inserted += 1
            return [node, ast.If(test=condition, body=body, orelse=[])]
        return node


def install(
    runner: Any,
    *,
    early_success: bool = True,
    trace_enabled: bool = False,
    exact_deadline: bool = True,
) -> dict[str, Any]:
    """Install optimized run_game into ``runner`` and return transform metadata."""

    if getattr(runner, "_SIM_V2_HOTPATCHED", False):
        return dict(getattr(runner, "_SIM_V2_HOTPATCH_META", {}))

    source = textwrap.dedent(inspect.getsource(runner.run_game))
    tree = ast.parse(source)
    tx = _RunGameTransform(
        early_success=early_success,
        trace_enabled=trace_enabled,
        exact_deadline=exact_deadline,
    )
    tree = tx.visit(tree)
    ast.fix_missing_locations(tree)
    if tx.early_exit_inserted == 0 and early_success:
        raise RuntimeError("sim-v2 hotpatch could not locate protectedAttempt assignment")
    if tx.trace_replaced == 0 and not trace_enabled:
        raise RuntimeError("sim-v2 hotpatch could not locate trace initialization")
    if tx.deadline_exit_inserted == 0 and exact_deadline:
        raise RuntimeError("sim-v2 hotpatch could not locate round update for exact deadline")

    runner.__dict__["_V2_TRACE_SINK"] = _TraceSink
    runner.__dict__["_V2_EARLY_SUCCESS"] = bool(early_success)
    runner.__dict__["_V2_EXACT_DEADLINE"] = bool(exact_deadline)
    filename = inspect.getsourcefile(runner.run_game) or "<sim-v2-run-game>"
    compiled = compile(tree, filename=filename, mode="exec")
    exec(compiled, runner.__dict__, runner.__dict__)
    meta = {
        "earlySuccess": bool(early_success),
        "exactDeadline": bool(exact_deadline),
        "traceEnabled": bool(trace_enabled),
        "traceInitializersReplaced": tx.trace_replaced,
        "earlyExitSitesInserted": tx.early_exit_inserted,
        "deadlineExitSitesInserted": tx.deadline_exit_inserted,
    }
    runner._SIM_V2_HOTPATCHED = True
    runner._SIM_V2_HOTPATCH_META = meta
    return meta
