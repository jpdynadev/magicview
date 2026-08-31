#!/usr/bin/env python3
"""Live Forge protocol canary for the canonical pilot-v9 path.

This is intentionally not a game simulation and never creates ranking evidence.
It starts the pinned interactive harness, advances pregame prompts for the
external Kinnan seat, submits one real typed ``chooseAction`` selected by
pilot-v9, and proves Forge accepted it by reaching a later phase. Any missing
stable identity or state transition fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import manabrew_pilot_v9 as pilot

HERE = Path(__file__).resolve().parent
DECK_DIR = HERE / "decks"


def _parse_dck(path: Path, *, exact_kinnan_registration: bool) -> tuple[list[str], list[str]]:
    section = ""
    commanders: list[str] = []
    main: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.lower()
            continue
        if not line[0].isdigit() or " " not in line:
            continue
        count_text, name = line.split(" ", 1)
        cards = commanders if section == "[commander]" else main if section == "[main]" else None
        if cards is not None:
            cards.extend([name.split("|", 1)[0].strip()] * int(count_text))
    if exact_kinnan_registration:
        if len(commanders) != 1 or len(main) != 99 or len(set(main)) != 99:
            raise RuntimeError(f"invalid exact Kinnan registration: {path}")
    elif len(commanders) not in {1, 2} or len(commanders) + len(main) != 100:
        raise RuntimeError(f"invalid opponent Commander registration: {path}")
    return commanders, commanders + main


def _player(
    name: str,
    deck_file: str,
    *,
    ai: bool,
    exact_kinnan_registration: bool = False,
) -> dict[str, Any]:
    commanders, cards = _parse_dck(
        DECK_DIR / deck_file,
        exact_kinnan_registration=exact_kinnan_registration,
    )
    return {
        "name": name,
        "commanderNames": commanders,
        "deck": [{"name": card} for card in cards],
        "ai": ai,
    }


def _rpc(proc: subprocess.Popen[str], request: dict[str, Any]) -> str:
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("Forge interactive harness closed stdout")
    response = json.loads(line)
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "Forge RPC failed"))
    return str(response.get("result") or "")


def _submit(proc: subprocess.Popen[str], session_id: str, answer: dict[str, Any]) -> None:
    _rpc(
        proc,
        {
            "command": "submitAction",
            "sessionId": session_id,
            "payload": json.dumps(answer, separators=(",", ":")),
        },
    )


def _pregame_answer(prompt_type: str) -> dict[str, Any] | None:
    if prompt_type in {"revealCards", "diceRolled"}:
        return {"type": prompt_type, "output": {}}
    if prompt_type == "mulligan":
        return {"type": "mulligan", "output": {"type": "mulliganDecision", "keep": True}}
    return None


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def run_canary(args: argparse.Namespace) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schemaVersion": "kinnan-v9-live-forge-canary-v2",
        "pilotVersion": pilot.PILOT_VERSION,
        "policyVersion": pilot.POLICY_VERSION,
        "purpose": "component-canary",
        "rankingEvidence": False,
        "seed": args.seed,
        "status": "starting",
        "valid": False,
        "promptTrace": [],
    }
    stderr_path = args.report.with_suffix(".stderr.log")
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stderr_path.open("w") as stderr_file:
        proc = subprocess.Popen(
            [
                "java",
                "-Xms192m",
                "-Xmx1280m",
                "-jar",
                args.harness_jar,
                "--interactive-server",
                "--forge-home",
                args.forge_home,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            bufsize=1,
        )
        session_id = ""
        try:
            payload = {
                "gameId": f"kinnan-v9-live-canary-{args.seed}",
                "variant": "Commander",
                "startingLife": 40,
                "seed": args.seed,
                "players": [
                    _player(
                        "Kinnan pilot-v9 external",
                        args.deck,
                        ai=False,
                        exact_kinnan_registration=True,
                    ),
                    _player("RogSi AI", "RogSi_2026.dck", ai=True),
                    _player("Blue Farm AI", "Blue_Farm_2026.dck", ai=True),
                    _player("RogThras AI", "RogThras_2026.dck", ai=True),
                ],
            }
            start = json.loads(
                _rpc(
                    proc,
                    {
                        "command": "startGame",
                        "payload": json.dumps(payload, separators=(",", ":")),
                    },
                )
            )
            session_id = str(start["sessionId"])
            deadline = time.monotonic() + args.max_seconds
            last_prompt_id = None
            submitted_witness: dict[str, Any] | None = None
            pre_action_snapshot_hash = ""
            post_action_snapshot_hash = ""
            while time.monotonic() < deadline:
                raw_prompt = _rpc(
                    proc,
                    {"command": "getPrompt", "sessionId": session_id, "playerIndex": 0},
                )
                if not raw_prompt:
                    time.sleep(0.05)
                    continue
                prompt = json.loads(raw_prompt)
                prompt_id = prompt.get("promptId")
                if prompt_id == last_prompt_id:
                    time.sleep(0.05)
                    continue
                last_prompt_id = prompt_id
                snapshot = json.loads(
                    _rpc(
                        proc,
                        {"command": "getSnapshot", "sessionId": session_id, "viewer": 0},
                    )
                )
                inp = prompt.get("input") or {}
                prompt_type = str(inp.get("type") or "")
                report["promptTrace"].append(
                    {
                        "promptId": prompt_id,
                        "promptType": prompt_type,
                        "turn": snapshot.get("turn"),
                        "step": snapshot.get("step"),
                    }
                )
                if submitted_witness is not None:
                    current_snapshot_hash = _stable_hash(snapshot)
                    if not post_action_snapshot_hash and current_snapshot_hash != pre_action_snapshot_hash:
                        post_action_snapshot_hash = current_snapshot_hash
                    submitted_turn = submitted_witness["snapshotTurn"]
                    submitted_step = submitted_witness["snapshotStep"]
                    phase_advanced = (
                        snapshot.get("turn") != submitted_turn
                        or snapshot.get("step") != submitted_step
                    )
                    if post_action_snapshot_hash and phase_advanced:
                        transition = {
                            "fromPromptId": submitted_witness["promptId"],
                            "toPromptId": prompt_id,
                            "fromTurn": submitted_turn,
                            "fromStep": submitted_step,
                            "toTurn": snapshot.get("turn"),
                            "toStep": snapshot.get("step"),
                        }
                        deterministic_witness = {
                            "action": submitted_witness,
                            "transition": transition,
                        }
                        report.update(
                            {
                                "status": "typed_action_applied_and_phase_advanced",
                                "valid": True,
                                "typedActionIdsComplete": True,
                                "witness": submitted_witness,
                                "transition": transition,
                                "preActionSnapshotHash": pre_action_snapshot_hash,
                                "postActionSnapshotHash": post_action_snapshot_hash,
                                "deterministicWitnessHash": _stable_hash(deterministic_witness),
                            }
                        )
                        return report
                if prompt_type == "chooseAction":
                    actions = list(inp.get("actions") or [])
                    if not actions:
                        report["promptTrace"][-1]["actionCount"] = 0
                        report["promptTrace"][-1]["forcedPass"] = True
                        report["emptyActionPrompts"] = int(report.get("emptyActionPrompts") or 0) + 1
                        _submit(
                            proc,
                            session_id,
                            {
                                "type": "chooseAction",
                                "output": {"type": "pass", "exhaustStack": False},
                            },
                        )
                        continue
                    if submitted_witness is not None:
                        report["promptTrace"][-1]["actionCount"] = len(actions)
                        report["promptTrace"][-1]["boundedPass"] = True
                        _submit(
                            proc,
                            session_id,
                            {
                                "type": "chooseAction",
                                "output": {"type": "pass", "exhaustStack": False},
                            },
                        )
                        continue
                    action_ids = [str(action.get("actionId") or action.get("id") or "") for action in actions]
                    if not all(action_ids) or len(set(action_ids)) != len(action_ids):
                        raise RuntimeError("live Forge actions lack unique stable action identity")
                    chosen = pilot.choose_action(
                        actions,
                        snapshot,
                        player_id=str(prompt.get("decidingPlayerId") or "player-0"),
                    )
                    if chosen is None:
                        raise RuntimeError("pilot-v9 returned no choice for a non-empty live action set")
                    chosen_id = str(chosen.get("actionId") or chosen.get("id") or "")
                    if chosen_id not in set(action_ids):
                        raise RuntimeError("pilot-v9 selected an action outside the live legal set")
                    witness = {
                        "promptId": prompt_id,
                        "promptType": prompt_type,
                        "actionCount": len(actions),
                        "actionIds": action_ids,
                        "chosenActionId": chosen_id,
                        "snapshotTurn": snapshot.get("turn"),
                        "snapshotStep": snapshot.get("step"),
                        "priorityPlayerId": snapshot.get("priorityPlayerId"),
                    }
                    pre_action_snapshot_hash = _stable_hash(snapshot)
                    submitted_witness = witness
                    report.update(
                        {
                            "status": "typed_action_submitted",
                            "typedActionIdsComplete": True,
                            "witness": witness,
                        }
                    )
                    _submit(
                        proc,
                        session_id,
                        {
                            "type": "chooseAction",
                            "output": {"type": "act", "actionId": chosen_id},
                        },
                    )
                    continue

                answer = _pregame_answer(prompt_type)
                if answer is None:
                    raise RuntimeError(
                        f"unsupported pregame prompt before typed action canary: {prompt_type!r}"
                    )
                _submit(proc, session_id, answer)
            if submitted_witness is not None:
                raise RuntimeError("timed out before the submitted live action advanced Forge state")
            raise RuntimeError("timed out before a live typed chooseAction prompt")
        finally:
            disposal_mode = "terminate"
            disposal_confirmed = False
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                disposal_mode = "kill"
                proc.kill()
                proc.wait(timeout=10)
            disposal_confirmed = proc.poll() is not None
            report["jvmDisposal"] = {
                "mode": disposal_mode,
                "confirmed": disposal_confirmed,
                "returnCode": proc.returncode,
            }
            if not disposal_confirmed:
                report["status"] = "failed_closed"
                report["valid"] = False
                report["error"] = "Forge JVM disposal was not confirmed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical pilot-v9 live Forge component canary")
    parser.add_argument("harness_jar")
    parser.add_argument("forge_home")
    parser.add_argument(
        "--deck",
        default="Kinnan_Sterling_TopDeck_Invitational_2026.dck",
    )
    parser.add_argument("--seed", type=int, default=1999000)
    parser.add_argument("--max-seconds", type=int, default=90)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_canary(args)
    except Exception as exc:
        report = {
            "schemaVersion": "kinnan-v9-live-forge-canary-v2",
            "pilotVersion": pilot.PILOT_VERSION,
            "policyVersion": pilot.POLICY_VERSION,
            "purpose": "component-canary",
            "rankingEvidence": False,
            "seed": args.seed,
            "status": "failed_closed",
            "valid": False,
            "error": repr(exc),
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
