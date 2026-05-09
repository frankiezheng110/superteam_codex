from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent_registry import agent_spawn_contract, require_superteam_agent
from .event_tree import (
    G4_EVENT_IDS,
    active_event,
    blocked_event,
    child_events,
    event_by_id,
    g4_event_nodes,
    mark_active_event_terminal,
    transition_to_phase,
)
from .state import StateError, is_g3_complete, load_mode, save_mode, validate_mode
from .tdd import (
    TDD_SIGNALS,
    apply_tdd_signal,
    assert_tdd_complete,
    assert_ui_guidance_complete,
    ensure_tdd_state,
    execution_tdd_evidence_errors,
    mark_active_ui_guidance,
    render_tdd_execution_markdown,
)
from .workspace import Workspace, file_sha256, read_json, utc_now, write_text


EXECUTOR_AGENT = require_superteam_agent("executor", context="G4.SPAWN_EXECUTOR")
INSPECTOR_AGENT = require_superteam_agent("inspector", context="G4.READINESS_CHECK")


def _event_tree_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    tree = mode.setdefault("event_tree", [])
    if not isinstance(tree, list):
        raise StateError("mode.event_tree is missing or invalid")
    return tree


def _ensure_g4_event_tree(mode: dict[str, Any]) -> bool:
    existing = {item.get("id") for item in _event_tree_items(mode) if isinstance(item, dict)}
    if all(event_id in existing for event_id in G4_EVENT_IDS) and "G4.RECORD_EVIDENCE" not in existing:
        return False
    tree = [
        item
        for item in _event_tree_items(mode)
        if not (isinstance(item, dict) and item.get("phase") == "G4" and item.get("id") != "G4")
    ]
    mode["event_tree"] = tree + g4_event_nodes()
    if event_by_id(mode, "G4").get("status") == "active":
        event_by_id(mode, "G4.START")["status"] = "active"
    return True


def _event(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    try:
        return event_by_id(mode, event_id)
    except KeyError as exc:
        raise StateError(str(exc)) from exc


def _active_g4_event(mode: dict[str, Any]) -> dict[str, Any]:
    current = active_event(mode, "G4")
    if current is None:
        blocked = blocked_event(mode, "G4")
        if blocked is not None:
            raise StateError(f"G4 is blocked at {blocked.get('id')}: {blocked.get('blocked_reason', '')}")
        raise StateError("G4 must have exactly one active event before completion")
    return current


def _path_in_run(mode: dict[str, Any], name: str) -> Path:
    return Path(mode["run_dir"]) / name


def execution_path(mode: dict[str, Any]) -> Path:
    return _path_in_run(mode, "05-execution.md")


def _contract(mode: dict[str, Any]) -> dict[str, Any]:
    contract = mode.setdefault("g4_contract", {})
    contract.setdefault("status", "pending")
    contract.setdefault("execution_plan", None)
    contract.setdefault("executor", None)
    contract.setdefault("execution_evidence", None)
    contract.setdefault("polish", None)
    contract.setdefault("tdd", {})
    contract.setdefault("repair_context", None)
    return contract


def _hook_trace(mode: dict[str, Any]) -> list[dict[str, Any]]:
    trace = mode.setdefault("hook_trace", [])
    if not isinstance(trace, list):
        trace = []
        mode["hook_trace"] = trace
    return trace


def _repair_iteration(mode: dict[str, Any]) -> int:
    repair_loop = mode.get("repair_loop") if isinstance(mode.get("repair_loop"), dict) else {}
    try:
        return int(repair_loop.get("active_iteration") or 0)
    except (TypeError, ValueError):
        return 0


def _has_hook(mode: dict[str, Any], hook: str) -> bool:
    iteration = _repair_iteration(mode)
    for item in _hook_trace(mode):
        if not isinstance(item, dict) or item.get("hook") != hook:
            continue
        try:
            item_iteration = int(item.get("repair_iteration") or 0)
        except (TypeError, ValueError):
            item_iteration = 0
        if item_iteration == iteration:
            return True
    return False


def _trace_g4_hook(
    mode: dict[str, Any],
    hook: str,
    trigger: str,
    event_id: str,
    instruction: str,
    extra: dict[str, Any] | None = None,
) -> None:
    event = _event(mode, event_id)
    record: dict[str, Any] = {
        "ts": utc_now(),
        "hook": hook,
        "trigger": trigger,
        "stage": mode.get("stage"),
        "node": event_id,
        "active_leaf_event": event_id,
        "soft_constraint": event.get("title") or event.get("hook_policy") or "",
        "instruction": instruction,
        "repair_iteration": _repair_iteration(mode),
    }
    if extra:
        record.update(extra)
    _hook_trace(mode).append(record)


def _trace_g4_hook_once(
    mode: dict[str, Any],
    hook: str,
    trigger: str,
    event_id: str,
    instruction: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if not _has_hook(mode, hook):
        _trace_g4_hook(mode, hook, trigger, event_id, instruction, extra)


def _orchestrator_state(mode: dict[str, Any]) -> dict[str, Any]:
    state = mode.setdefault("orchestrator", {})
    state.setdefault("role", "main_session_orchestrator")
    state.setdefault("agent_calls", [])
    state.setdefault("spawn_decision", "not_required")
    state.setdefault("spawn_status", "not_required")
    state.setdefault("expected_agent", None)
    state.setdefault("active_event", None)
    state.setdefault("hook_instruction", "")
    return state


def _inspector_state(mode: dict[str, Any]) -> dict[str, Any]:
    state = mode.setdefault("inspector", {})
    state.setdefault("status", "not_run")
    state.setdefault("active_event", None)
    state.setdefault("checkpoint_required", False)
    state.setdefault("gate_check_report", {"status": "not_run", "checked_event": None, "findings": []})
    state.setdefault("trace_coverage", {"status": "not_run", "missing_events": [], "discrepancies": []})
    return state


def _set_orchestrator(
    mode: dict[str, Any],
    event_id: str,
    *,
    spawn_decision: str,
    spawn_status: str,
    expected_agent: str | None,
    instruction: str,
) -> None:
    state = _orchestrator_state(mode)
    state["active_event"] = event_id
    state["spawn_decision"] = spawn_decision
    state["spawn_status"] = spawn_status
    state["expected_agent"] = expected_agent
    state["expected_agent_definition"] = agent_spawn_contract(expected_agent) if expected_agent else None
    state["hook_instruction"] = instruction


def _set_inspector(
    mode: dict[str, Any],
    event_id: str,
    *,
    status: str,
    checkpoint_required: bool,
    agent_id: str | None = None,
) -> None:
    state = _inspector_state(mode)
    state["active_event"] = event_id
    state["status"] = status
    state["checkpoint_required"] = checkpoint_required
    state["agent_id"] = agent_id
    state["gate_check_report"] = {"status": "not_required", "checked_event": event_id, "findings": []}
    state["trace_coverage"] = {"status": "pass", "missing_events": [], "discrepancies": []}


def _record_agent_call(
    mode: dict[str, Any],
    event_id: str,
    agent: str,
    agent_id: str,
    status: str,
    scope: str,
) -> None:
    calls = _orchestrator_state(mode).setdefault("agent_calls", [])
    if not isinstance(calls, list):
        calls = []
        _orchestrator_state(mode)["agent_calls"] = calls
    calls.append(
        {
            "ts": utc_now(),
            "event": event_id,
            "role": agent,
            "agent_id": agent_id,
            "scope": scope,
            "status": status,
            **agent_spawn_contract(agent),
        }
    )


def _has_agent_call(mode: dict[str, Any], event_id: str, agent: str) -> bool:
    calls = _orchestrator_state(mode).get("agent_calls") or []
    return any(isinstance(item, dict) and item.get("event") == event_id and item.get("role") == agent for item in calls)


def _complete_agent_call(mode: dict[str, Any], event_id: str, agent: str, note: str) -> str:
    calls = _orchestrator_state(mode).get("agent_calls") or []
    for item in reversed(calls):
        if isinstance(item, dict) and item.get("event") == event_id and item.get("role") == agent:
            item["status"] = "completed"
            item["completed_at"] = utc_now()
            item["result_note"] = note.strip()
            return str(item.get("agent_id") or "")
    raise StateError(f"{event_id} requires {agent} spawn_record before result")


def _complete_current(mode: dict[str, Any], event_id: str) -> dict[str, Any] | None:
    current = _event(mode, event_id)
    current["completed_at"] = utc_now()
    try:
        next_event = mark_active_event_terminal(mode, event_id, "done")
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    _trace_g4_hook(mode, f"{event_id}.record", "runtime recorded event result", event_id, f"record {event_id}")
    if next_event is not None:
        next_id = str(next_event.get("id") or "")
        _trace_g4_hook(mode, f"{event_id}.next", f"{event_id}=done", event_id, f"advance to {next_id}")
        _trace_g4_hook_once(mode, f"{next_id}.enter", f"{next_id}=active", next_id, "enter active G4 event")
        _set_orchestrator(
            mode,
            next_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction=f"complete {next_id} or stop at its hook gate",
        )
        _set_inspector(mode, next_id, status="not_required", checkpoint_required=False)
    return next_event


def _load_execution_plan(mode: dict[str, Any]) -> dict[str, Any]:
    path = _path_in_run(mode, "implementation-plan.json")
    plan = read_json(path, None)
    if not isinstance(plan, dict):
        raise StateError("implementation-plan.json is missing or invalid")
    return plan


def _executor_agent_id(mode: dict[str, Any]) -> str:
    calls = _orchestrator_state(mode).get("agent_calls") or []
    for item in reversed(calls):
        if isinstance(item, dict) and item.get("event") == "G4.SPAWN_EXECUTOR" and item.get("role") == EXECUTOR_AGENT:
            return str(item.get("agent_id") or f"{EXECUTOR_AGENT}-local")
    return f"{EXECUTOR_AGENT}-local"


def _write_execution_artifact(mode: dict[str, Any], note: str) -> Path:
    path = execution_path(mode)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if "agent_type: executor" in existing and "Status: implementation_complete" in existing:
            _contract(mode)["execution_evidence"] = {
                "path": str(path.resolve()),
                "sha256": file_sha256(path),
                "recorded_at": utc_now(),
            }
            return path

    plan = _contract(mode).get("execution_plan") or _load_execution_plan(mode)
    items = plan.get("work_items") if isinstance(plan, dict) else []
    lines = [
        "---",
        f"agent_type: {EXECUTOR_AGENT}",
        f"agent_id: {_executor_agent_id(mode)}",
        f"task_slug: {mode.get('active_task_slug')}",
        "---",
        "",
        "# G4 Execution",
        "",
        "Status: recorded",
        "",
        "## Executor Result",
        "",
        note.strip() or "Executor completed the approved G3 work items.",
        "",
    ]
    if isinstance(items, list) and items:
        ensure_tdd_state(mode, plan)
        lines.extend(render_tdd_execution_markdown(mode))
    else:
        lines.extend(["## Work Items", "", "- No structured work items were found in implementation-plan.json."])
        lines.extend(["", "## Execution Summary", "", "- TDD exception: NO", "- TDD status: not_required"])
    lines.extend(["", "## Evidence", "", "- Executor result was recorded through hook-trace."])
    write_text(path, "\n".join(lines) + "\n")
    _contract(mode)["execution_evidence"] = {
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "recorded_at": utc_now(),
    }
    return path


def _write_polish_artifact(mode: dict[str, Any]) -> Path:
    path = _path_in_run(mode, "polish.md")
    if not path.exists():
        write_text(
            path,
            "\n".join(
                [
                    "---",
                    "agent_type: executor",
                    f"agent_id: {_executor_agent_id(mode)}",
                    f"task_slug: {mode.get('active_task_slug')}",
                    "---",
                    "",
                    "# Post-Execute Polish",
                    "",
                    "Status: not_applicable",
                    "",
                    "No separate polish worker was required by the G4 hook-trace test.",
                    "",
                ]
            ),
        )
    _contract(mode)["polish"] = {"path": str(path.resolve()), "sha256": file_sha256(path)}
    return path


def _ensure_g4_spawn_required(mode: dict[str, Any]) -> None:
    event_id = "G4.SPAWN_EXECUTOR"
    _trace_g4_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter executor spawn gate")
    repair_context = _contract(mode).get("repair_context")
    if isinstance(repair_context, dict) and repair_context:
        iteration = repair_context.get("iteration") or _repair_iteration(mode)
        _trace_g4_hook_once(
            mode,
            f"G4.REPAIR_GUIDANCE.iteration_{iteration}",
            "g6_verification_failed",
            event_id,
            "guide executor before repair: fix the failed G6 verification items, preserve unrelated completed work, then repeat TDD and evidence",
            {"repair_context": repair_context},
        )
    _trace_g4_hook_once(
        mode,
        f"{event_id}.spawn_required",
        f"expected_agent={EXECUTOR_AGENT}",
        event_id,
        "spawn executor for approved G3 plan",
        {"expected_agent": EXECUTOR_AGENT, **agent_spawn_contract(EXECUTOR_AGENT)},
    )
    ui_guidance = _ensure_g4_ui_guidance(mode, event_id, "executor spawn gate")
    instruction = "spawn executor; main session must not implement G4 directly"
    if isinstance(repair_context, dict) and repair_context:
        instruction = f"{instruction}; repair iteration {repair_context.get('iteration')}: fix G6 {repair_context.get('verdict')} findings before broad changes"
    if ui_guidance and ui_guidance.get("contract"):
        instruction = f"{instruction}; first UI work item must follow G3 UI contract before implementation: {ui_guidance['contract']}"
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=EXECUTOR_AGENT,
        instruction=instruction,
    )
    _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)


def _ensure_g4_ui_guidance(mode: dict[str, Any], event_id: str, source: str) -> dict[str, Any] | None:
    guidance = mark_active_ui_guidance(mode, source=source)
    if not guidance:
        return None
    work_item_id = str(guidance.get("work_item_id") or "")
    hook = f"G4.UI_GUIDANCE.{work_item_id}"
    if not _has_hook(mode, hook):
        contract = str(guidance.get("contract") or "")
        _trace_g4_hook(
            mode,
            hook,
            f"active_ui_work_item={work_item_id}",
            event_id,
            f"guide executor before UI implementation: {contract}",
            {"ui_guidance": guidance},
        )
    return guidance


def _require_g4_inspector(mode: dict[str, Any], event_id: str) -> None:
    _trace_g4_hook_once(
        mode,
        f"{event_id}.inspector_required",
        f"expected_agent={INSPECTOR_AGENT}",
        event_id,
        "spawn inspector to check G4 readiness before review",
        {"expected_agent": INSPECTOR_AGENT, **agent_spawn_contract(INSPECTOR_AGENT)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=INSPECTOR_AGENT,
        instruction="spawn inspector; OR must not impersonate Inspector",
    )
    inspector = _inspector_state(mode)
    inspector["status"] = "waiting_for_spawn_record"
    inspector["active_event"] = event_id
    inspector["checkpoint_required"] = True
    inspector["pending_event"] = event_id
    inspector["agent_id"] = None


def _record_g4_inspector_spawn(mode: dict[str, Any], event_id: str, agent_id: str) -> None:
    call_id = agent_id.strip() or f"{INSPECTOR_AGENT}-local"
    _record_agent_call(mode, event_id, INSPECTOR_AGENT, call_id, "spawned", f"inspect {event_id} trace before review")
    _trace_g4_hook(mode, f"{event_id}.inspector_spawn_record", f"agent_id={call_id}", event_id, "record inspector spawn", {"agent": INSPECTOR_AGENT, "agent_id": call_id, **agent_spawn_contract(INSPECTOR_AGENT)})
    _trace_g4_hook_once(mode, f"{event_id}.inspector_wait_result", "waiting for inspector result", event_id, "wait for inspector result")
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="spawned",
        spawn_status="waiting_result",
        expected_agent=INSPECTOR_AGENT,
        instruction="wait for inspector result",
    )
    inspector = _inspector_state(mode)
    inspector["status"] = "waiting_for_agent_result"
    inspector["agent_id"] = call_id


def _record_g4_inspector_result(mode: dict[str, Any], event_id: str, note: str) -> None:
    agent_id = _complete_agent_call(mode, event_id, INSPECTOR_AGENT, note)
    _trace_g4_hook(mode, f"{event_id}.inspector_result_record", note.strip() or "inspector completed", event_id, "record inspector result", {"agent": INSPECTOR_AGENT, "agent_id": agent_id})
    _trace_g4_hook(mode, f"{event_id}.inspector_check", "inspector trace coverage pass", event_id, "inspector gate check pass", {"agent": INSPECTOR_AGENT, "agent_id": agent_id})
    inspector = _inspector_state(mode)
    inspector["status"] = "not_required"
    inspector["checkpoint_required"] = False
    inspector["gate_check_report"] = {"status": "pass", "checked_event": event_id, "findings": []}
    inspector["trace_coverage"] = {"status": "pass", "missing_events": [], "discrepancies": []}


def _assert_g4_ready(mode: dict[str, Any]) -> None:
    for event_id in [
        "G4.START",
        "G4.LOAD_APPROVED_PLAN",
        "G4.CHECK_G3_APPROVED",
        "G4.SPAWN_EXECUTOR",
        "G4.EXECUTE_WORK_ITEMS",
        "G4.RECORD_EXECUTION_EVIDENCE",
        "G4.OPTIONAL_POLISH",
    ]:
        if _event(mode, event_id).get("status") != "done":
            raise StateError(f"{event_id} must be done before G4.READINESS_CHECK")
    if not execution_path(mode).exists():
        raise StateError("05-execution.md is missing before G4.READINESS_CHECK")
    assert_tdd_complete(mode)
    assert_ui_guidance_complete(mode)
    execution_text = execution_path(mode).read_text(encoding="utf-8")
    tdd_errors = execution_tdd_evidence_errors(mode, execution_text)
    if tdd_errors:
        raise StateError("G4 execution evidence TDD gate blocked: " + "; ".join(tdd_errors))


def advance_g4(ws: Workspace, note: str = "") -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g4_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "execute":
        raise StateError("G4 can only advance while stage=execute")
    current = _active_g4_event(mode)
    event_id = str(current.get("id"))
    contract = _contract(mode)

    if event_id == "G4.START":
        if not is_g3_complete(mode):
            raise StateError("G4.START requires G3.COMPLETE")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G4.LOAD_APPROVED_PLAN":
        if not _path_in_run(mode, "04-plan.md").exists():
            raise StateError("04-plan.md is missing before G4")
        plan = _load_execution_plan(mode)
        contract["execution_plan"] = plan
        ensure_tdd_state(mode, plan)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G4.CHECK_G3_APPROVED":
        if (mode.get("g3_approval") or {}).get("status") != "approved":
            raise StateError("G3 approval must be approved before G4 execution")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G4.SPAWN_EXECUTOR":
        raise StateError("G4.SPAWN_EXECUTOR requires executor spawn/result through g4-trace")

    elif event_id == "G4.EXECUTE_WORK_ITEMS":
        if not (contract.get("executor") or {}).get("result_note"):
            raise StateError("G4.EXECUTE_WORK_ITEMS requires executor result")
        assert_tdd_complete(mode)
        assert_ui_guidance_complete(mode)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G4.RECORD_EXECUTION_EVIDENCE":
        if not execution_path(mode).exists():
            raise StateError("05-execution.md is missing")
        contract["execution_evidence"] = {
            "path": str(execution_path(mode).resolve()),
            "sha256": file_sha256(execution_path(mode)),
            "recorded_at": utc_now(),
        }
        next_event = _complete_current(mode, event_id)

    elif event_id == "G4.OPTIONAL_POLISH":
        _write_polish_artifact(mode)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G4.READINESS_CHECK":
        raise StateError("G4.READINESS_CHECK requires inspector spawn/result through g4-trace")

    elif event_id == "G4.COMPLETE":
        current["completed_at"] = utc_now()
        current["status"] = "done"
        _trace_g4_hook(mode, "G4.COMPLETE.record", "runtime recorded event result", "G4.COMPLETE", "record G4 completion")
        transition_to_phase(mode, "G5")
        _trace_g4_hook(mode, "G4.COMPLETE.next", "G4.COMPLETE=done", "G4.COMPLETE", "advance to G5")
        next_g5 = active_event(mode, "G5")
        next_id = str(next_g5.get("id") if next_g5 else "G5")
        _set_orchestrator(
            mode,
            next_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction="G4 complete; enter G5 review",
        )
        _set_inspector(mode, next_id, status="not_required", checkpoint_required=False)
        contract["status"] = "done"
        mode["status"] = "review_ready"
        save_mode(ws, mode)
        return {
            "ok": True,
            "event": "G4.COMPLETE",
            "next_global_event": "G5",
            "next_event": next_id,
            "execution": str(execution_path(mode).resolve()),
        }

    else:
        raise StateError(f"unsupported G4 event: {event_id}")

    mode["status"] = f"{event_id.lower()}_done"
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": event_id,
        "status": "done",
        "next_event": next_event.get("id") if next_event else None,
        "execution": str(execution_path(mode).resolve()),
    }


def run_g4_hook_trace_until_stage_gate(ws: Workspace, before_index: int | None = None) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g4_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "execute":
        raise StateError("G4 hook-trace can only run while stage=execute")
    if before_index is None:
        before_index = len(_hook_trace(mode))
    advanced: list[dict[str, Any]] = []

    while True:
        current = _active_g4_event(mode)
        event_id = str(current.get("id"))
        if event_id == "G4.SPAWN_EXECUTOR":
            _ensure_g4_spawn_required(mode)
            mode["status"] = "g4_spawn_executor_waiting_for_spawn"
            save_mode(ws, mode)
            return _g4_trace_result(mode, before_index, advanced)
        if event_id == "G4.READINESS_CHECK":
            _assert_g4_ready(mode)
            _require_g4_inspector(mode, event_id)
            mode["status"] = "g4_readiness_waiting_for_inspector_spawn"
            save_mode(ws, mode)
            return _g4_trace_result(mode, before_index, advanced)
        result = advance_g4(ws)
        advanced.append({"event": result["event"], "next_event": result.get("next_event")})
        mode = load_mode(ws)
        assert mode is not None
        _ensure_g4_event_tree(mode)
        if mode.get("stage") != "execute":
            return _g4_trace_result(mode, before_index, advanced)


def apply_g4_hook_trace_signal(
    ws: Workspace,
    signal: str,
    note: str = "",
    *,
    agent: str = "",
    agent_id: str = "",
    work_item_id: str = "",
    command: str = "",
    test_file: str = "",
    passed: int | None = None,
    failed: int | None = None,
) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g4_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    before_index = len(_hook_trace(mode))
    current = _active_g4_event(mode)
    event_id = str(current.get("id"))

    if signal in TDD_SIGNALS:
        if event_id != "G4.SPAWN_EXECUTOR":
            raise StateError(f"active G4 event is {event_id}; cannot record TDD evidence")
        if not _has_agent_call(mode, event_id, EXECUTOR_AGENT):
            raise StateError(f"{event_id} requires spawn_record before TDD evidence")
        ui_guidance = None
        if signal in {"tdd-red", "tdd-blocked", "tdd-deferred"}:
            ui_guidance = _ensure_g4_ui_guidance(mode, event_id, f"before {signal}")
        tdd_result = apply_tdd_signal(
            mode,
            signal,
            note,
            work_item_id=work_item_id.strip(),
            command=command.strip(),
            test_file=test_file.strip(),
            passed=passed,
            failed=failed,
        )
        hook_suffix = signal.replace("-", "_")
        instruction = "record G4 TDD evidence"
        active_tdd = (_contract(mode).get("tdd") or {}).get("active_work_item_id")
        if signal == "tdd-next" and not active_tdd:
            instruction = "G4 TDD complete; wait for executor result"
        elif active_tdd:
            instruction = f"continue G4 TDD for {active_tdd}"
        _trace_g4_hook(
            mode,
            f"G4.TDD.{hook_suffix}",
            note.strip() or signal,
            event_id,
            instruction,
            {"tdd": tdd_result},
        )
        if signal == "tdd-next":
            ui_guidance = _ensure_g4_ui_guidance(mode, event_id, "after tdd-next")
        if ui_guidance and ui_guidance.get("contract"):
            instruction = f"{instruction}; follow G3 UI contract before implementation: {ui_guidance['contract']}"
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="waiting_result",
            expected_agent=EXECUTOR_AGENT,
            instruction=instruction,
        )
        _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
        mode["status"] = f"g4_{hook_suffix}_recorded"
        save_mode(ws, mode)
        return _g4_trace_result(mode, before_index, [])

    if signal == "spawn-record":
        if event_id != "G4.SPAWN_EXECUTOR":
            raise StateError(f"active G4 event is {event_id}; cannot record executor spawn")
        expected_agent = EXECUTOR_AGENT
        agent_name = agent.strip() or expected_agent
        if agent_name != expected_agent:
            raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")
        _ensure_g4_spawn_required(mode)
        call_id = agent_id.strip() or f"{agent_name}-local"
        _record_agent_call(mode, event_id, agent_name, call_id, "spawned", "execute the approved G3 plan")
        _trace_g4_hook(mode, f"{event_id}.spawn_record", f"agent_id={call_id}", event_id, f"record {agent_name} spawn", {"agent": agent_name, "agent_id": call_id, **agent_spawn_contract(agent_name)})
        _trace_g4_hook_once(mode, f"{event_id}.wait_result", "waiting for executor result", event_id, "wait for executor result")
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="waiting_result",
            expected_agent=expected_agent,
            instruction="wait for executor result",
        )
        _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
        mode["status"] = "g4_spawn_executor_waiting_for_result"
        save_mode(ws, mode)
        return _g4_trace_result(mode, before_index, [])

    if signal == "agent-result":
        if event_id != "G4.SPAWN_EXECUTOR":
            raise StateError(f"active G4 event is {event_id}; cannot record executor result")
        expected_agent = EXECUTOR_AGENT
        agent_name = agent.strip() or expected_agent
        if agent_name != expected_agent:
            raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")
        if not _has_agent_call(mode, event_id, expected_agent):
            raise StateError(f"{event_id} requires spawn_record before agent-result")
        assert_tdd_complete(mode)
        assert_ui_guidance_complete(mode)
        agent_call_id = _complete_agent_call(mode, event_id, expected_agent, note)
        _contract(mode)["executor"] = {
            "agent_id": agent_call_id,
            "result_note": note.strip(),
            "completed_at": utc_now(),
        }
        _write_execution_artifact(mode, note)
        _trace_g4_hook(mode, f"{event_id}.result_record", note.strip() or "executor completed", event_id, "record executor result", {"agent": expected_agent, "agent_id": agent_call_id})
        next_event = _complete_current(mode, event_id)
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="completed",
            expected_agent=expected_agent,
            instruction=f"executor completed; advance to {next_event.get('id') if next_event else 'next'}",
        )
        mode["status"] = "g4_executor_result_recorded"
        save_mode(ws, mode)
        return run_g4_hook_trace_until_stage_gate(ws, before_index)

    if signal == "inspector-spawn-record":
        if _inspector_state(mode).get("pending_event") != event_id:
            raise StateError(f"active G4 event is {event_id}; no inspector check is pending")
        agent_name = agent.strip() or INSPECTOR_AGENT
        if agent_name != INSPECTOR_AGENT:
            raise StateError(f"{event_id} requires agent {INSPECTOR_AGENT}, got {agent_name}")
        _record_g4_inspector_spawn(mode, event_id, agent_id)
        mode["status"] = "g4_readiness_waiting_for_inspector_result"
        save_mode(ws, mode)
        return _g4_trace_result(mode, before_index, [])

    if signal == "inspector-result":
        if _inspector_state(mode).get("pending_event") != event_id:
            raise StateError(f"active G4 event is {event_id}; no inspector check is pending")
        if not _has_agent_call(mode, event_id, INSPECTOR_AGENT):
            raise StateError(f"{event_id} requires inspector_spawn_record before inspector-result")
        _record_g4_inspector_result(mode, event_id, note)
        if event_id != "G4.READINESS_CHECK":
            raise StateError(f"unsupported G4 inspector event: {event_id}")
        next_event = _complete_current(mode, event_id)
        _inspector_state(mode).pop("pending_event", None)
        mode["status"] = "g4_readiness_done"
        save_mode(ws, mode)
        return run_g4_hook_trace_until_stage_gate(ws, before_index)

    raise StateError(
        "signal must be one of: spawn-record, agent-result, inspector-spawn-record, inspector-result, "
        + ", ".join(sorted(TDD_SIGNALS))
    )


def _g4_trace_result(mode: dict[str, Any], before_index: int, advanced: list[dict[str, Any]]) -> dict[str, Any]:
    current_event = None
    if mode.get("stage") == "execute":
        current = active_event(mode, "G4") or blocked_event(mode, "G4")
        current_event = current.get("id") if current else None
    trace = _hook_trace(mode)
    return {
        "ok": True,
        "active_event": current_event,
        "active_global_event": (active_event(mode) or {}).get("id") if mode.get("stage") == "execute" else "G5",
        "complete": _event(mode, "G4.COMPLETE").get("status") == "done",
        "advanced": advanced,
        "trace_hooks": [item.get("hook") for item in trace[before_index:] if isinstance(item, dict)],
        "events": child_events(mode, "G4"),
        "contract": _contract(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "execution": str(execution_path(mode).resolve()),
    }


def g4_status(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    _ensure_g4_event_tree(mode)
    save_mode(ws, mode)
    current = active_event(mode, "G4") or blocked_event(mode, "G4")
    return {
        "ok": True,
        "active_event": current.get("id") if current else None,
        "complete": _event(mode, "G4.COMPLETE").get("status") == "done",
        "events": child_events(mode, "G4"),
        "contract": _contract(mode),
        "hook_trace": _hook_trace(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "execution": str(execution_path(mode).resolve()),
    }
