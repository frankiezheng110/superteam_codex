from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from superteam_codex.runtime.doctor import run_doctor
    from superteam_codex.runtime.g1 import (
        apply_g1_hook_trace_signal,
        g1_status,
        record_g1_answer,
        run_g1_hook_trace_until_user_gate,
    )
    from superteam_codex.runtime.g1_guided_hooks import run_g1_guided_simulation
    from superteam_codex.runtime.g2 import (
        apply_g2_hook_trace_signal,
        g2_status,
        run_g2_hook_trace_until_user_gate,
    )
    from superteam_codex.runtime.g3 import (
        apply_g3_hook_trace_signal,
        g3_status,
        run_g3_hook_trace_until_user_gate,
    )
    from superteam_codex.runtime.g4 import (
        apply_g4_hook_trace_signal,
        g4_status,
        run_g4_hook_trace_until_stage_gate,
    )
    from superteam_codex.runtime.g5 import (
        apply_g5_hook_trace_signal,
        g5_status,
        run_g5_hook_trace_until_stage_gate,
    )
    from superteam_codex.runtime.g6 import (
        apply_g6_hook_trace_signal,
        g6_status,
        run_g6_hook_trace_until_stage_gate,
    )
    from superteam_codex.runtime.g7 import (
        apply_g7_hook_trace_signal,
        g7_status,
        run_g7_hook_trace_until_stage_gate,
    )
    from superteam_codex.runtime.g2_guided_hooks import run_g2_guided_simulation
    from superteam_codex.runtime.stages import (
        StageError,
        rebuild_active_map,
        refresh_active_event_tree,
        reset_workspace,
        start_run,
        status_summary,
    )
    from superteam_codex.runtime.state import StateError, set_lifecycle
    from superteam_codex.runtime.workspace import Workspace, write_json
else:
    from .runtime.doctor import run_doctor
    from .runtime.g1 import (
        apply_g1_hook_trace_signal,
        g1_status,
        record_g1_answer,
        run_g1_hook_trace_until_user_gate,
    )
    from .runtime.g1_guided_hooks import run_g1_guided_simulation
    from .runtime.g2 import (
        apply_g2_hook_trace_signal,
        g2_status,
        run_g2_hook_trace_until_user_gate,
    )
    from .runtime.g3 import (
        apply_g3_hook_trace_signal,
        g3_status,
        run_g3_hook_trace_until_user_gate,
    )
    from .runtime.g4 import (
        apply_g4_hook_trace_signal,
        g4_status,
        run_g4_hook_trace_until_stage_gate,
    )
    from .runtime.g5 import (
        apply_g5_hook_trace_signal,
        g5_status,
        run_g5_hook_trace_until_stage_gate,
    )
    from .runtime.g6 import (
        apply_g6_hook_trace_signal,
        g6_status,
        run_g6_hook_trace_until_stage_gate,
    )
    from .runtime.g7 import (
        apply_g7_hook_trace_signal,
        g7_status,
        run_g7_hook_trace_until_stage_gate,
    )
    from .runtime.g2_guided_hooks import run_g2_guided_simulation
    from .runtime.stages import (
        StageError,
        rebuild_active_map,
        refresh_active_event_tree,
        reset_workspace,
        start_run,
        status_summary,
    )
    from .runtime.state import StateError, set_lifecycle
    from .runtime.workspace import Workspace, write_json


def _print(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _workspace(args: argparse.Namespace) -> Workspace:
    return Workspace(Path(args.project or "."))


def cmd_go(args: argparse.Namespace) -> int:
    task = " ".join(args.task).strip()
    if not task:
        task = "SuperTeam Codex run"
    _print(start_run(_workspace(args), task, force=args.force))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    _print(status_summary(_workspace(args)))
    return 0


def cmd_map(args: argparse.Namespace) -> int:
    _print(rebuild_active_map(_workspace(args)))
    return 0


def cmd_repair_event_tree(args: argparse.Namespace) -> int:
    _print(refresh_active_event_tree(_workspace(args)))
    return 0


def cmd_g1_status(args: argparse.Namespace) -> int:
    _print(g1_status(_workspace(args)))
    return 0


def cmd_g1_answer(args: argparse.Namespace) -> int:
    answer = " ".join(args.answer).strip()
    _print(record_g1_answer(_workspace(args), answer, status=args.status))
    return 0


def cmd_g1_summary(args: argparse.Namespace) -> int:
    _print(run_g1_hook_trace_until_user_gate(_workspace(args)))
    return 0


def cmd_g1_approve(args: argparse.Namespace) -> int:
    _print(apply_g1_hook_trace_signal(_workspace(args), "approve-g1", note=args.note or ""))
    return 0


def cmd_g1_trace(args: argparse.Namespace) -> int:
    note = " ".join(args.note or []).strip()
    if args.signal:
        _print(
            apply_g1_hook_trace_signal(
                _workspace(args),
                args.signal,
                note=note,
                status=args.status,
                agent=args.agent,
                agent_id=args.agent_id,
            )
        )
    else:
        _print(run_g1_hook_trace_until_user_gate(_workspace(args)))
    return 0


def cmd_simulate_g1(args: argparse.Namespace) -> int:
    _print(
        run_g1_guided_simulation(
            task=args.task,
            answers=args.answer or None,
            end_signal=args.end_signal,
            approval=args.approval,
        )
    )
    return 0


def cmd_g2_status(args: argparse.Namespace) -> int:
    _print(g2_status(_workspace(args)))
    return 0


def cmd_g2_next(args: argparse.Namespace) -> int:
    _print(run_g2_hook_trace_until_user_gate(_workspace(args)))
    return 0


def cmd_g2_approve(args: argparse.Namespace) -> int:
    _print(apply_g2_hook_trace_signal(_workspace(args), "approve-g2", note=args.note or ""))
    return 0


def cmd_g2_approve_plan(args: argparse.Namespace) -> int:
    _print(apply_g2_hook_trace_signal(_workspace(args), "approve-plan", note=args.note or ""))
    return 0


def cmd_g2_design_step(args: argparse.Namespace) -> int:
    note = " ".join(args.note).strip()
    _print(apply_g2_hook_trace_signal(_workspace(args), "design-step", note=note, complete=args.complete))
    return 0


def cmd_g2_trace(args: argparse.Namespace) -> int:
    note = " ".join(args.note or []).strip()
    if args.signal:
        _print(
            apply_g2_hook_trace_signal(
                _workspace(args),
                args.signal,
                note=note,
                complete=args.complete,
                agent=args.agent,
                agent_id=args.agent_id,
            )
        )
    else:
        _print(run_g2_hook_trace_until_user_gate(_workspace(args)))
    return 0


def cmd_simulate_g2(args: argparse.Namespace) -> int:
    _print(
        run_g2_guided_simulation(
            features=args.feature or None,
            ui_plan=args.plan_item or None,
            plan_approval=args.plan_approval,
            design_done_signal=args.design_done_signal,
            approval=args.approval,
        )
    )
    return 0


def cmd_g3_status(args: argparse.Namespace) -> int:
    _print(g3_status(_workspace(args)))
    return 0


def cmd_g3_next(args: argparse.Namespace) -> int:
    _print(run_g3_hook_trace_until_user_gate(_workspace(args)))
    return 0


def cmd_g3_approve(args: argparse.Namespace) -> int:
    _print(apply_g3_hook_trace_signal(_workspace(args), "approve-g3", note=args.note or ""))
    return 0


def cmd_g3_trace(args: argparse.Namespace) -> int:
    note = " ".join(args.note or []).strip()
    if args.signal:
        _print(
            apply_g3_hook_trace_signal(
                _workspace(args),
                args.signal,
                note=note,
                agent=args.agent,
                agent_id=args.agent_id,
                work_item_id=args.work_item,
                command=args.command,
                test_file=args.test_file,
                passed=args.passed,
                failed=args.failed,
            )
        )
    else:
        _print(run_g3_hook_trace_until_user_gate(_workspace(args)))
    return 0


def cmd_g4_status(args: argparse.Namespace) -> int:
    _print(g4_status(_workspace(args)))
    return 0


def cmd_g4_next(args: argparse.Namespace) -> int:
    _print(run_g4_hook_trace_until_stage_gate(_workspace(args)))
    return 0


def cmd_g4_trace(args: argparse.Namespace) -> int:
    note = " ".join(args.note or []).strip()
    if args.signal:
        _print(
            apply_g4_hook_trace_signal(
                _workspace(args),
                args.signal,
                note=note,
                agent=args.agent,
                agent_id=args.agent_id,
                work_item_id=args.work_item,
                command=args.command,
                test_file=args.test_file,
                passed=args.passed,
                failed=args.failed,
            )
        )
    else:
        _print(run_g4_hook_trace_until_stage_gate(_workspace(args)))
    return 0


def cmd_g5_status(args: argparse.Namespace) -> int:
    _print(g5_status(_workspace(args)))
    return 0


def cmd_g5_next(args: argparse.Namespace) -> int:
    _print(run_g5_hook_trace_until_stage_gate(_workspace(args)))
    return 0


def cmd_g5_trace(args: argparse.Namespace) -> int:
    note = " ".join(args.note or []).strip()
    if args.signal:
        _print(
            apply_g5_hook_trace_signal(
                _workspace(args),
                args.signal,
                note=note,
                agent=args.agent,
                agent_id=args.agent_id,
                severity=args.severity,
            )
        )
    else:
        _print(run_g5_hook_trace_until_stage_gate(_workspace(args)))
    return 0


def cmd_g6_status(args: argparse.Namespace) -> int:
    _print(g6_status(_workspace(args)))
    return 0


def cmd_g6_next(args: argparse.Namespace) -> int:
    _print(run_g6_hook_trace_until_stage_gate(_workspace(args)))
    return 0


def cmd_g6_trace(args: argparse.Namespace) -> int:
    note = " ".join(args.note or []).strip()
    if args.signal:
        _print(
            apply_g6_hook_trace_signal(
                _workspace(args),
                args.signal,
                note=note,
                agent=args.agent,
                agent_id=args.agent_id,
                severity=args.severity,
            )
        )
    else:
        _print(run_g6_hook_trace_until_stage_gate(_workspace(args)))
    return 0


def cmd_g7_status(args: argparse.Namespace) -> int:
    _print(g7_status(_workspace(args)))
    return 0


def cmd_g7_next(args: argparse.Namespace) -> int:
    _print(run_g7_hook_trace_until_stage_gate(_workspace(args)))
    return 0


def cmd_g7_trace(args: argparse.Namespace) -> int:
    note = " ".join(args.note or []).strip()
    if args.signal:
        _print(
            apply_g7_hook_trace_signal(
                _workspace(args),
                args.signal,
                note=note,
                agent=args.agent,
                agent_id=args.agent_id,
            )
        )
    else:
        _print(run_g7_hook_trace_until_stage_gate(_workspace(args)))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    result = run_doctor(_workspace(args))
    _print(result)
    return 0 if result["health"] != "fail" else 1


def cmd_lifecycle(args: argparse.Namespace) -> int:
    status = {
        "pause": "paused_by_user",
        "resume": "resumed_by_user",
        "end": "ended_by_user",
    }[args.lifecycle]
    lifecycle = {
        "pause": "paused",
        "resume": "running",
        "end": "ended",
    }[args.lifecycle]
    _print({"ok": True, "mode": set_lifecycle(_workspace(args), lifecycle, status)})
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    _print(reset_workspace(_workspace(args), confirm=args.confirm))
    return 0


def cmd_project_init(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    ws.ensure()
    milestones = [
        {"slug": item, "status": "pending", "title": item.replace("-", " ")}
        for item in args.milestone
    ]
    project = {
        "schema": "superteam_codex.project.v1",
        "plugin": "superteam_codex",
        "project_root": str(ws.root),
        "status": "in_progress",
        "name": args.name,
        "current_milestone_slug": milestones[0]["slug"] if milestones else None,
        "milestones": milestones,
        "runs": [],
    }
    write_json(ws.project_path, project)
    _print({"ok": True, "project": project})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="superteam-codex")
    parser.add_argument("--project", default=".", help="Target project root.")
    sub = parser.add_subparsers(dest="command", required=True)

    go = sub.add_parser("go", help="Start a new SuperTeam Codex run.")
    go.add_argument("task", nargs="*", help="Task text.")
    go.add_argument("--force", action="store_true", help="Start even if an active run exists.")
    go.set_defaults(func=cmd_go)

    status = sub.add_parser("status", help="Show current run status.")
    status.set_defaults(func=cmd_status)

    map_cmd = sub.add_parser("map", help="Rebuild source manifest, frame inventory, and feature UI map.")
    map_cmd.set_defaults(func=cmd_map)

    repair_event_tree = sub.add_parser("repair-event-tree", help="Refresh legacy event_tree to the current hook-trace schema.")
    repair_event_tree.set_defaults(func=cmd_repair_event_tree)

    g1_status_cmd = sub.add_parser("g1-status", help="Show the G1 event table.")
    g1_status_cmd.set_defaults(func=cmd_g1_status)

    g1_answer = sub.add_parser("g1-answer", help="Record an answer for the active G1 question.")
    g1_answer.add_argument(
        "--status",
        choices=["done", "deferred", "not_applicable"],
        default="done",
        help="Terminal status for the active question.",
    )
    g1_answer.add_argument("answer", nargs="+", help="Answer text for the active G1 question.")
    g1_answer.set_defaults(func=cmd_g1_answer)

    g1_summary = sub.add_parser("g1-summary", help="Run G1 hook-trace to the summary spawn/approval gate.")
    g1_summary.set_defaults(func=cmd_g1_summary)

    g1_approve = sub.add_parser("g1-approve", help="Record G1 approval through hook-trace and require Inspector.")
    g1_approve.add_argument("--note", default="", help="Optional user approval note.")
    g1_approve.set_defaults(func=cmd_g1_approve)

    g1_trace = sub.add_parser("g1-trace", help="Run the designed G1 hook-trace flow until the next gate.")
    g1_trace.add_argument(
        "--signal",
        choices=["answer", "spawn-record", "agent-result", "inspector-spawn-record", "inspector-result", "approve-g1"],
        default=None,
        help="Record a user, spawn, or agent signal before continuing the hook-trace flow.",
    )
    g1_trace.add_argument(
        "--status",
        choices=["done", "deferred", "not_applicable"],
        default="done",
        help="Terminal status for an answer signal.",
    )
    g1_trace.add_argument("--agent", default="", help="Agent role for spawn-record or inspector-spawn-record.")
    g1_trace.add_argument("--agent-id", default="", help="Concrete agent id for spawn-record or inspector-spawn-record.")
    g1_trace.add_argument("note", nargs="*", help="Answer, approval, spawn note, or agent-result note.")
    g1_trace.set_defaults(func=cmd_g1_trace)

    simulate_g1 = sub.add_parser("simulate-g1", help="Run the guided-hook design from project start through G1.")
    simulate_g1.add_argument("--task", default="构建一个 SuperTeam Codex 示例项目")
    simulate_g1.add_argument("--answer", action="append", default=[], help="Repeat exactly seven times to override the default G1 answers.")
    simulate_g1.add_argument("--end-signal", default="下一个")
    simulate_g1.add_argument("--approval", default="确认 G1")
    simulate_g1.set_defaults(func=cmd_simulate_g1)

    g2_status_cmd = sub.add_parser("g2-status", help="Show the G2 event subtree and contract.")
    g2_status_cmd.set_defaults(func=cmd_g2_status)

    g2_next = sub.add_parser("g2-next", help="Run G2 hook-trace until the next spawn or user gate.")
    g2_next.add_argument("--note", default="", help="Optional note for source review or contract context.")
    g2_next.set_defaults(func=cmd_g2_next)

    g2_approve = sub.add_parser("g2-approve", help="Record G2 approval through hook-trace and require Inspector.")
    g2_approve.add_argument("--note", default="", help="Optional user approval note.")
    g2_approve.set_defaults(func=cmd_g2_approve)

    g2_approve_plan = sub.add_parser("g2-approve-plan", help="Record G2 UI design-plan approval through hook-trace.")
    g2_approve_plan.add_argument("--note", default="", help="Optional user approval note.")
    g2_approve_plan.set_defaults(func=cmd_g2_approve_plan)

    g2_design_step = sub.add_parser("g2-design-step", help="Record user-steered Pencil design progress through hook-trace.")
    g2_design_step.add_argument("--complete", action="store_true", help="Complete G2.DESIGN_PENCIL_STEPS after the user design-done signal.")
    g2_design_step.add_argument("note", nargs="+", help="Design step note.")
    g2_design_step.set_defaults(func=cmd_g2_design_step)

    g2_trace = sub.add_parser("g2-trace", help="Run the designed G2 hook-trace flow until the next user gate.")
    g2_trace.add_argument(
        "--signal",
        choices=["spawn-record", "agent-result", "inspector-spawn-record", "inspector-result", "approve-plan", "design-step", "approve-g2"],
        default=None,
        help="Record a user interaction signal before continuing the hook-trace flow.",
    )
    g2_trace.add_argument("--agent", default="", help="Agent role for spawn-record, agent-result, or inspector-spawn-record.")
    g2_trace.add_argument("--agent-id", default="", help="Agent invocation id for spawn-record or inspector-spawn-record.")
    g2_trace.add_argument("--complete", action="store_true", help="Complete G2.DESIGN_PENCIL_STEPS with this design-step signal.")
    g2_trace.add_argument("note", nargs="*", help="User signal note or design step note.")
    g2_trace.set_defaults(func=cmd_g2_trace)

    simulate_g2 = sub.add_parser("simulate-g2", help="Run the guided-hook design from G2 start through G2 delivery.")
    simulate_g2.add_argument("--feature", action="append", default=[], help="Repeat to override G1 feature checklist.")
    simulate_g2.add_argument("--plan-item", action="append", default=[], help="Repeat to override the UI design plan.")
    simulate_g2.add_argument("--plan-approval", default="确认 UI 设计计划")
    simulate_g2.add_argument("--design-done-signal", default="设计完成")
    simulate_g2.add_argument("--approval", default="确认 G2")
    simulate_g2.set_defaults(func=cmd_simulate_g2)

    g3_status_cmd = sub.add_parser("g3-status", help="Show the G3 event subtree and execution-plan contract.")
    g3_status_cmd.set_defaults(func=cmd_g3_status)

    g3_next = sub.add_parser("g3-next", help="Run G3 hook-trace until the next spawn or user gate.")
    g3_next.set_defaults(func=cmd_g3_next)

    g3_approve = sub.add_parser("g3-approve", help="Record G3 approval through hook-trace and require Inspector.")
    g3_approve.add_argument("--note", default="", help="Optional user approval note.")
    g3_approve.set_defaults(func=cmd_g3_approve)

    g3_trace = sub.add_parser("g3-trace", help="Run the designed G3 hook-trace flow until the next user gate.")
    g3_trace.add_argument(
        "--signal",
        choices=["spawn-record", "agent-result", "inspector-spawn-record", "inspector-result", "approve-g3"],
        default=None,
        help="Record a spawn, agent, inspector, or approval signal before continuing the hook-trace flow.",
    )
    g3_trace.add_argument("--agent", default="", help="Agent role for spawn-record, agent-result, or inspector-spawn-record.")
    g3_trace.add_argument("--agent-id", default="", help="Agent invocation id for spawn-record or inspector-spawn-record.")
    g3_trace.add_argument("note", nargs="*", help="User signal note or agent-result note.")
    g3_trace.set_defaults(func=cmd_g3_trace)

    g4_status_cmd = sub.add_parser("g4-status", help="Show the G4 event subtree and execution contract.")
    g4_status_cmd.set_defaults(func=cmd_g4_status)

    g4_next = sub.add_parser("g4-next", help="Run G4 hook-trace until the next executor or inspector gate.")
    g4_next.set_defaults(func=cmd_g4_next)

    g4_trace = sub.add_parser("g4-trace", help="Run the designed G4 hook-trace flow until the next automatic gate.")
    g4_trace.add_argument(
        "--signal",
        choices=[
            "spawn-record",
            "agent-result",
            "inspector-spawn-record",
            "inspector-result",
            "tdd-red",
            "tdd-green",
            "tdd-next",
            "tdd-blocked",
            "tdd-deferred",
        ],
        default=None,
        help="Record an executor or inspector signal before continuing the G4 hook-trace flow.",
    )
    g4_trace.add_argument("--agent", default="", help="Agent role for spawn-record, agent-result, or inspector-spawn-record.")
    g4_trace.add_argument("--agent-id", default="", help="Agent invocation id for spawn-record or inspector-spawn-record.")
    g4_trace.add_argument("--work-item", default="", help="G4 work item id for TDD evidence signals.")
    g4_trace.add_argument("--command", default="", help="Test command for tdd-red or tdd-green.")
    g4_trace.add_argument("--test-file", default="", help="Test file path for tdd-red or tdd-green.")
    g4_trace.add_argument("--passed", type=int, default=None, help="Passing test count for TDD evidence.")
    g4_trace.add_argument("--failed", type=int, default=None, help="Failing test count for TDD evidence.")
    g4_trace.add_argument("note", nargs="*", help="Signal note or agent-result note.")
    g4_trace.set_defaults(func=cmd_g4_trace)

    g5_status_cmd = sub.add_parser("g5-status", help="Show the G5 event subtree and review contract.")
    g5_status_cmd.set_defaults(func=cmd_g5_status)

    g5_next = sub.add_parser("g5-next", help="Run G5 hook-trace until the next reviewer or designer gate.")
    g5_next.set_defaults(func=cmd_g5_next)

    g5_trace = sub.add_parser("g5-trace", help="Run the designed G5 hook-trace flow until the next automatic gate.")
    g5_trace.add_argument(
        "--signal",
        choices=["spawn-record", "agent-result", "review-finding"],
        default=None,
        help="Record a reviewer/designer signal or immediate review finding before continuing the G5 hook-trace flow.",
    )
    g5_trace.add_argument("--agent", default="", help="Agent role for spawn-record or agent-result.")
    g5_trace.add_argument("--agent-id", default="", help="Agent invocation id for spawn-record.")
    g5_trace.add_argument("--severity", default="", help="Severity for review-finding signals.")
    g5_trace.add_argument("note", nargs="*", help="Signal note, review finding, or agent-result note.")
    g5_trace.set_defaults(func=cmd_g5_trace)

    g6_status_cmd = sub.add_parser("g6-status", help="Show the G6 event subtree and verification contract.")
    g6_status_cmd.set_defaults(func=cmd_g6_status)

    g6_next = sub.add_parser("g6-next", help="Run G6 hook-trace until the verifier gate or G7.")
    g6_next.set_defaults(func=cmd_g6_next)

    g6_trace = sub.add_parser("g6-trace", help="Run the designed G6 hook-trace flow until the next automatic gate.")
    g6_trace.add_argument(
        "--signal",
        choices=["spawn-record", "agent-result", "verification-finding"],
        default=None,
        help="Record a verifier signal or verification finding before continuing the G6 hook-trace flow.",
    )
    g6_trace.add_argument("--agent", default="", help="Agent role for spawn-record or agent-result.")
    g6_trace.add_argument("--agent-id", default="", help="Agent invocation id for spawn-record.")
    g6_trace.add_argument("--severity", default="", help="Severity for verification-finding signals.")
    g6_trace.add_argument("note", nargs="*", help="Signal note, verification finding, or agent-result note.")
    g6_trace.set_defaults(func=cmd_g6_trace)

    g7_status_cmd = sub.add_parser("g7-status", help="Show the G7 event subtree and finish contract.")
    g7_status_cmd.set_defaults(func=cmd_g7_status)

    g7_next = sub.add_parser("g7-next", help="Run G7 hook-trace until the inspector/writer gate or completion.")
    g7_next.set_defaults(func=cmd_g7_next)

    g7_trace = sub.add_parser("g7-trace", help="Run the designed G7 hook-trace flow until the next automatic gate.")
    g7_trace.add_argument(
        "--signal",
        choices=["spawn-record", "agent-result"],
        default=None,
        help="Record an inspector or writer signal before continuing the G7 hook-trace flow.",
    )
    g7_trace.add_argument("--agent", default="", help="Agent role for spawn-record or agent-result.")
    g7_trace.add_argument("--agent-id", default="", help="Agent invocation id for spawn-record.")
    g7_trace.add_argument("note", nargs="*", help="Signal note or agent-result note.")
    g7_trace.set_defaults(func=cmd_g7_trace)

    doctor = sub.add_parser("doctor", help="Run health checks.")
    doctor.set_defaults(func=cmd_doctor)

    reset = sub.add_parser("reset", help="Move .superteam_codex to a timestamped backup.")
    reset.add_argument("--confirm", action="store_true", help="Required to perform reset.")
    reset.set_defaults(func=cmd_reset)

    for name in ["pause", "resume", "end"]:
        cmd = sub.add_parser(name, help=f"{name} the active run.")
        cmd.set_defaults(func=cmd_lifecycle, lifecycle=name)

    project_init = sub.add_parser("project-init", help="Create project-level milestone state.")
    project_init.add_argument("--name", required=True)
    project_init.add_argument("--milestone", action="append", default=[])
    project_init.set_defaults(func=cmd_project_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (StageError, StateError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
