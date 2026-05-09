from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .agent_registry import agent_spawn_contract, require_superteam_agent
from .event_tree import (
    G7_EVENT_IDS,
    active_event,
    blocked_event,
    child_events,
    event_by_id,
    g7_event_nodes,
    mark_active_event_terminal,
)
from .state import StateError, load_mode, save_mode, validate_mode
from .workspace import Workspace, file_sha256, read_json, utc_now, write_json


INSPECTOR_AGENT = require_superteam_agent("inspector", context="G7.SPAWN_INSPECTOR")
WRITER_AGENT = require_superteam_agent("writer", context="G7.SPAWN_WRITER")

FINISH_INPUT_FILES = [
    "01-project-definition.md",
    "02-design.md",
    "04-plan.md",
    "05-execution.md",
    "06-review.md",
    "07-verification.md",
    "implementation-plan.json",
    "ui-code-map.json",
    "visual-acceptance.json",
]


def _event_tree_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    tree = mode.setdefault("event_tree", [])
    if not isinstance(tree, list):
        raise StateError("mode.event_tree is missing or invalid")
    return tree


def _ensure_g7_event_tree(mode: dict[str, Any]) -> bool:
    existing = {item.get("id") for item in _event_tree_items(mode) if isinstance(item, dict)}
    if all(event_id in existing for event_id in G7_EVENT_IDS) and "G7.WRITE_HANDOFF" not in existing:
        return False
    tree = [
        item
        for item in _event_tree_items(mode)
        if not (isinstance(item, dict) and item.get("phase") == "G7" and item.get("id") != "G7")
    ]
    mode["event_tree"] = tree + g7_event_nodes()
    if event_by_id(mode, "G7").get("status") == "active":
        event_by_id(mode, "G7.START")["status"] = "active"
    return True


def _event(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    try:
        return event_by_id(mode, event_id)
    except KeyError as exc:
        raise StateError(str(exc)) from exc


def _active_g7_event(mode: dict[str, Any]) -> dict[str, Any]:
    if _event(mode, "G7.COMPLETE").get("status") == "done":
        raise StateError("G7 is already complete")
    current = active_event(mode, "G7")
    if current is None:
        blocked = blocked_event(mode, "G7")
        if blocked is not None:
            raise StateError(f"G7 is blocked at {blocked.get('id')}: {blocked.get('blocked_reason', '')}")
        raise StateError("G7 must have exactly one active event before completion")
    return current


def _path_in_run(mode: dict[str, Any], name: str) -> Path:
    return Path(mode["run_dir"]) / name


def finish_path(mode: dict[str, Any]) -> Path:
    return _path_in_run(mode, "08-finish.md")


def retrospective_path(mode: dict[str, Any]) -> Path:
    return _path_in_run(mode, "retrospective.md")


def inspector_report_path(mode: dict[str, Any]) -> Path:
    slug = str(mode.get("active_task_slug") or "run")
    return Path(mode["project_root"]) / ".superteam_codex" / "inspector" / "reports" / f"{slug}-report.md"


def _contract(mode: dict[str, Any]) -> dict[str, Any]:
    contract = mode.setdefault("g7_contract", {})
    contract.setdefault("status", "pending")
    contract.setdefault("finish_inputs", [])
    contract.setdefault("inspector", None)
    contract.setdefault("inspector_report", None)
    contract.setdefault("writer", None)
    contract.setdefault("finish_artifacts", {})
    return contract


def _hook_trace(mode: dict[str, Any]) -> list[dict[str, Any]]:
    trace = mode.setdefault("hook_trace", [])
    if not isinstance(trace, list):
        trace = []
        mode["hook_trace"] = trace
    return trace


def _has_hook(mode: dict[str, Any], hook: str) -> bool:
    return any(isinstance(item, dict) and item.get("hook") == hook for item in _hook_trace(mode))


def _trace_g7_hook(
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
    }
    if extra:
        record.update(extra)
    _hook_trace(mode).append(record)


def _trace_g7_hook_once(
    mode: dict[str, Any],
    hook: str,
    trigger: str,
    event_id: str,
    instruction: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if not _has_hook(mode, hook):
        _trace_g7_hook(mode, hook, trigger, event_id, instruction, extra)


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
    state.setdefault("status", "not_required")
    state.setdefault("active_event", None)
    state.setdefault("checkpoint_required", False)
    state.setdefault("gate_check_report", {"status": "not_required", "checked_event": None, "findings": []})
    state.setdefault("trace_coverage", {"status": "pass", "missing_events": [], "discrepancies": []})
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


def _set_inspector_state(mode: dict[str, Any], event_id: str, *, status: str, checkpoint_required: bool) -> None:
    inspector = _inspector_state(mode)
    inspector["active_event"] = event_id
    inspector["status"] = status
    inspector["checkpoint_required"] = checkpoint_required
    inspector["gate_check_report"] = {"status": status, "checked_event": event_id, "findings": []}
    inspector["trace_coverage"] = {"status": "pass", "missing_events": [], "discrepancies": []}


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


def _has_agent_call(mode: dict[str, Any], event_id: str, agent: str, *, status: str | None = None) -> bool:
    calls = _orchestrator_state(mode).get("agent_calls") or []
    for item in calls:
        if not isinstance(item, dict):
            continue
        if item.get("event") == event_id and item.get("role") == agent:
            if status is None or item.get("status") == status:
                return True
    return False


def _complete_agent_call(mode: dict[str, Any], event_id: str, agent: str, note: str) -> str:
    calls = _orchestrator_state(mode).get("agent_calls") or []
    for item in reversed(calls):
        if isinstance(item, dict) and item.get("event") == event_id and item.get("role") == agent:
            item["status"] = "completed"
            item["completed_at"] = utc_now()
            item["result_note"] = note.strip()
            return str(item.get("agent_id") or "")
    raise StateError(f"{event_id} requires {agent} spawn_record before result")


def _complete_current(mode: dict[str, Any], event_id: str, status: str = "done") -> dict[str, Any] | None:
    current = _event(mode, event_id)
    current["completed_at"] = utc_now()
    try:
        next_event = mark_active_event_terminal(mode, event_id, status)
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    _trace_g7_hook(mode, f"{event_id}.record", "runtime recorded event result", event_id, f"record {event_id}")
    if next_event is not None:
        next_id = str(next_event.get("id") or "")
        _trace_g7_hook(mode, f"{event_id}.next", f"{event_id}={status}", event_id, f"advance to {next_id}")
        _trace_g7_hook_once(mode, f"{next_id}.enter", f"{next_id}=active", next_id, "enter active G7 event")
        _set_orchestrator(
            mode,
            next_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction=f"complete {next_id} or stop at its hook gate",
        )
        _set_inspector_state(mode, next_id, status="not_required", checkpoint_required=False)
    return next_event


def _artifact_record(mode: dict[str, Any], name: str) -> dict[str, Any]:
    path = _path_in_run(mode, name)
    record: dict[str, Any] = {
        "name": name,
        "path": str(path.resolve()),
        "exists": path.exists(),
    }
    if path.exists() and path.is_file():
        record["sha256"] = file_sha256(path)
    return record


def _collect_finish_inputs(mode: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = [_artifact_record(mode, name) for name in FINISH_INPUT_FILES]
    report = inspector_report_path(mode)
    inputs.append(
        {
            "name": "inspector-report.md",
            "path": str(report.resolve()),
            "exists": report.exists(),
            **({"sha256": file_sha256(report)} if report.exists() and report.is_file() else {}),
        }
    )
    return inputs


def _verification_text(mode: dict[str, Any]) -> str:
    path = _path_in_run(mode, "07-verification.md")
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _verification_pass(mode: dict[str, Any]) -> bool:
    contract = mode.get("g6_contract") if isinstance(mode.get("g6_contract"), dict) else {}
    if contract.get("verdict") == "PASS" and contract.get("status") == "done":
        return True
    return bool(re.search(r"(?im)^\s*(?:verdict|status)\s*:\s*PASS\b", _verification_text(mode)))


def _trace_finish_inputs_guidance(mode: dict[str, Any], event_id: str) -> None:
    inputs = _collect_finish_inputs(mode)
    _contract(mode)["finish_inputs"] = inputs
    _trace_g7_hook_once(
        mode,
        "G7.FINISH_INPUTS_GUIDANCE",
        "before finish work",
        event_id,
        (
            "guide finish before any handoff work: use verifier PASS, review concerns, G1-G5 artifacts, "
            "full hook_trace, and event_tree; do not modify product code in G7"
        ),
        {"finish_inputs": inputs},
    )
    _trace_g7_hook_once(
        mode,
        "G7.NO_PRODUCT_CODE_CHANGE_GUIDANCE",
        "stage=finish",
        event_id,
        "guide G7 agents to limit work to inspector report, finish summary, and retrospective artifacts",
        {"allowed_outputs": [str(inspector_report_path(mode).resolve()), str(finish_path(mode).resolve()), str(retrospective_path(mode).resolve())]},
    )


def _ensure_inspector_required(mode: dict[str, Any]) -> None:
    event_id = "G7.SPAWN_INSPECTOR"
    _trace_g7_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter inspector spawn gate")
    _trace_finish_inputs_guidance(mode, event_id)
    _trace_g7_hook_once(
        mode,
        "G7.INSPECTOR_GUIDANCE",
        "before inspector spawn",
        event_id,
        (
            "guide inspector before audit: inspect hook_trace coverage, event_tree order, agent role boundaries, "
            "G1-G6 artifacts, bypasses, and process risks; inspector audits process, not product implementation"
        ),
        {"expected_report": str(inspector_report_path(mode).resolve())},
    )
    _trace_g7_hook_once(
        mode,
        f"{event_id}.spawn_required",
        f"expected_agent={INSPECTOR_AGENT}",
        event_id,
        "spawn inspector for SuperTeam process audit before writer handoff",
        {"expected_agent": INSPECTOR_AGENT, **agent_spawn_contract(INSPECTOR_AGENT)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=INSPECTOR_AGENT,
        instruction="spawn inspector; provide full hook_trace, event_tree, G1-G6 artifacts, and original SuperTeam inspector rules",
    )
    _set_inspector_state(mode, event_id, status="waiting_for_spawn_record", checkpoint_required=True)


def _ensure_writer_required(mode: dict[str, Any]) -> None:
    event_id = "G7.SPAWN_WRITER"
    _trace_g7_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter writer spawn gate")
    _trace_finish_inputs_guidance(mode, event_id)
    _trace_g7_hook_once(
        mode,
        "G7.FINISH_GUIDANCE",
        "before writer spawn",
        event_id,
        (
            "guide writer before handoff: summarize delivered scope, verifier PASS evidence, inspector report, "
            "review concerns, residual risks, and write retrospective with improvement_action"
        ),
        {
            "verification": str(_path_in_run(mode, "07-verification.md").resolve()),
            "inspector_report": str(inspector_report_path(mode).resolve()),
            "finish": str(finish_path(mode).resolve()),
            "retrospective": str(retrospective_path(mode).resolve()),
        },
    )
    _trace_g7_hook_once(
        mode,
        f"{event_id}.spawn_required",
        f"expected_agent={WRITER_AGENT}",
        event_id,
        "spawn writer to produce finish and retrospective artifacts after inspector report exists",
        {"expected_agent": WRITER_AGENT, **agent_spawn_contract(WRITER_AGENT)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=WRITER_AGENT,
        instruction="spawn writer; provide verifier PASS, inspector report, and finish artifact requirements",
    )
    _set_inspector_state(mode, event_id, status="not_required", checkpoint_required=False)


def _record_inspector_report(mode: dict[str, Any]) -> None:
    path = inspector_report_path(mode)
    if not path.exists():
        raise StateError(f"inspector report is missing: {path.resolve()}")
    _contract(mode)["inspector_report"] = {
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "recorded_at": utc_now(),
    }


def _record_finish_artifacts(mode: dict[str, Any]) -> None:
    artifacts: dict[str, Any] = {}
    for name, path in {
        "finish": finish_path(mode),
        "retrospective": retrospective_path(mode),
    }.items():
        if not path.exists():
            raise StateError(f"{path.name} is missing; writer must write finish artifacts before G7 can advance")
        artifacts[name] = {
            "path": str(path.resolve()),
            "sha256": file_sha256(path),
            "recorded_at": utc_now(),
        }
    _contract(mode)["finish_artifacts"] = artifacts


def finish_gate_errors(mode: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not _verification_pass(mode):
        errors.append("G7 finish requires G6 verifier verdict PASS")
    report = inspector_report_path(mode)
    if not report.exists():
        errors.append("G7 finish requires inspector report")
    finish = finish_path(mode)
    retro = retrospective_path(mode)
    if not finish.exists():
        errors.append("08-finish.md is missing")
    if not retro.exists():
        errors.append("retrospective.md is missing")
    finish_text = finish.read_text(encoding="utf-8") if finish.exists() else ""
    retro_text = retro.read_text(encoding="utf-8") if retro.exists() else ""
    if finish_text and not re.search(r"(?is)\bverifier\b.*\bPASS\b|\bPASS\b.*\bverifier\b", finish_text):
        errors.append("08-finish.md must acknowledge verifier PASS")
    if finish_text and not re.search(r"(?is)\binspector\b.*\b(report|acknowledged|acknowledgement)\b|inspector_report_acknowledged\s*:\s*true", finish_text):
        errors.append("08-finish.md must acknowledge inspector report")
    if retro_text and not re.search(r"(?im)^\s*improvement_action\s*:\s*\S+", retro_text):
        errors.append("retrospective.md must contain non-empty improvement_action")
    return errors


def _assert_g7_gate_ready(mode: dict[str, Any]) -> None:
    _record_inspector_report(mode)
    _record_finish_artifacts(mode)
    errors = finish_gate_errors(mode)
    if errors:
        raise StateError("G7 finish gate blocked: " + "; ".join(errors))


def _mark_project_complete(ws: Workspace, mode: dict[str, Any]) -> None:
    project = read_json(ws.project_path, None)
    if not isinstance(project, dict):
        return
    slug = mode.get("active_task_slug")
    for run in project.get("runs", []) if isinstance(project.get("runs"), list) else []:
        if isinstance(run, dict) and run.get("slug") == slug:
            run["status"] = "complete"
            run["completed_at"] = utc_now()
    project["status"] = "complete"
    project["updated_at"] = utc_now()
    write_json(ws.project_path, project)


def advance_g7(ws: Workspace, note: str = "") -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g7_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "finish":
        raise StateError("G7 can only advance while stage=finish")
    current = _active_g7_event(mode)
    event_id = str(current.get("id"))
    contract = _contract(mode)

    if event_id == "G7.START":
        if not _verification_pass(mode):
            raise StateError("G7.START requires G6 verifier PASS")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G7.LOAD_FINISH_INPUTS":
        contract["finish_inputs"] = _collect_finish_inputs(mode)
        _trace_finish_inputs_guidance(mode, event_id)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G7.CHECK_G6_PASS":
        if not _verification_pass(mode):
            raise StateError("G6 PASS is required before G7 finish")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G7.SPAWN_INSPECTOR":
        raise StateError("G7.SPAWN_INSPECTOR requires inspector spawn/result through g7-trace")

    elif event_id == "G7.RECORD_INSPECTOR_REPORT":
        if not (contract.get("inspector") or {}).get("result_note"):
            raise StateError("G7.RECORD_INSPECTOR_REPORT requires inspector result")
        _record_inspector_report(mode)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G7.SPAWN_WRITER":
        raise StateError("G7.SPAWN_WRITER requires writer spawn/result through g7-trace")

    elif event_id == "G7.WRITE_FINISH_ARTIFACTS":
        if not (contract.get("writer") or {}).get("result_note"):
            raise StateError("G7.WRITE_FINISH_ARTIFACTS requires writer result")
        _record_finish_artifacts(mode)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G7.CHECK_FINISH_GATE":
        _assert_g7_gate_ready(mode)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G7.COMPLETE":
        current["completed_at"] = utc_now()
        current["status"] = "done"
        _event(mode, "G7")["status"] = "done"
        _event(mode, "RUN")["status"] = "done"
        _trace_g7_hook(mode, "G7.COMPLETE.record", "runtime recorded event result", "G7.COMPLETE", "record G7 completion")
        contract["status"] = "done"
        contract["completed_at"] = utc_now()
        mode["status"] = "completed"
        mode["project_lifecycle"] = "complete"
        mode["mode"] = "inactive"
        _set_orchestrator(
            mode,
            "G7.COMPLETE",
            spawn_decision="not_required",
            spawn_status="not_required",
            expected_agent=None,
            instruction="SuperTeam Codex run complete",
        )
        _set_inspector_state(mode, "G7.COMPLETE", status="complete", checkpoint_required=False)
        _mark_project_complete(ws, mode)
        save_mode(ws, mode)
        return {
            "ok": True,
            "event": "G7.COMPLETE",
            "complete": True,
            "finish": str(finish_path(mode).resolve()),
            "retrospective": str(retrospective_path(mode).resolve()),
            "inspector_report": str(inspector_report_path(mode).resolve()),
        }

    else:
        raise StateError(f"unsupported G7 event: {event_id}")

    mode["status"] = f"{event_id.lower()}_done"
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": event_id,
        "status": "done",
        "next_event": next_event.get("id") if next_event else None,
        "finish": str(finish_path(mode).resolve()),
    }


def run_g7_hook_trace_until_stage_gate(ws: Workspace, before_index: int | None = None) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g7_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "finish":
        raise StateError("G7 hook-trace can only run while stage=finish")
    if before_index is None:
        before_index = len(_hook_trace(mode))
    advanced: list[dict[str, Any]] = []

    while True:
        if _event(mode, "G7.COMPLETE").get("status") == "done":
            return _g7_trace_result(mode, before_index, advanced)
        current = _active_g7_event(mode)
        event_id = str(current.get("id"))
        if event_id == "G7.SPAWN_INSPECTOR":
            _ensure_inspector_required(mode)
            mode["status"] = "g7_finish_waiting_for_inspector_spawn"
            save_mode(ws, mode)
            return _g7_trace_result(mode, before_index, advanced)
        if event_id == "G7.SPAWN_WRITER":
            _ensure_writer_required(mode)
            mode["status"] = "g7_finish_waiting_for_writer_spawn"
            save_mode(ws, mode)
            return _g7_trace_result(mode, before_index, advanced)
        result = advance_g7(ws)
        advanced.append({"event": result["event"], "next_event": result.get("next_event")})
        mode = load_mode(ws)
        assert mode is not None
        _ensure_g7_event_tree(mode)


def _expected_agent_for_event(event_id: str) -> str | None:
    if event_id == "G7.SPAWN_INSPECTOR":
        return INSPECTOR_AGENT
    if event_id == "G7.SPAWN_WRITER":
        return WRITER_AGENT
    return None


def apply_g7_hook_trace_signal(
    ws: Workspace,
    signal: str,
    note: str = "",
    *,
    agent: str = "",
    agent_id: str = "",
) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g7_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    before_index = len(_hook_trace(mode))
    current = _active_g7_event(mode)
    event_id = str(current.get("id"))
    expected_agent = _expected_agent_for_event(event_id)
    if expected_agent is None:
        raise StateError(f"active G7 event is {event_id}; no agent signal is pending")
    agent_name = agent.strip() or expected_agent
    if agent_name != expected_agent:
        raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")

    if signal == "spawn-record":
        if expected_agent == INSPECTOR_AGENT:
            _ensure_inspector_required(mode)
            scope = "audit SuperTeam process, hook_trace, event_tree, and role boundaries before finish"
        else:
            _ensure_writer_required(mode)
            scope = "write finish handoff and retrospective after verifier PASS and inspector report"
        call_id = agent_id.strip() or f"{agent_name}-local"
        _record_agent_call(mode, event_id, agent_name, call_id, "spawned", scope)
        _trace_g7_hook(mode, f"{event_id}.spawn_record", f"agent_id={call_id}", event_id, f"record {agent_name} spawn", {"agent": agent_name, "agent_id": call_id, **agent_spawn_contract(agent_name)})
        _trace_g7_hook_once(mode, f"{event_id}.wait_result", f"waiting for {agent_name} result", event_id, f"wait for {agent_name} result")
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="waiting_result",
            expected_agent=expected_agent,
            instruction=f"wait for {agent_name} result",
        )
        _set_inspector_state(
            mode,
            event_id,
            status="waiting_result" if expected_agent == INSPECTOR_AGENT else "not_required",
            checkpoint_required=expected_agent == INSPECTOR_AGENT,
        )
        mode["status"] = f"g7_{agent_name}_waiting_for_result"
        save_mode(ws, mode)
        return _g7_trace_result(mode, before_index, [])

    if signal == "agent-result":
        if not _has_agent_call(mode, event_id, expected_agent):
            raise StateError(f"{event_id} requires spawn_record before agent-result")
        if expected_agent == INSPECTOR_AGENT:
            _record_inspector_report(mode)
        else:
            _record_finish_artifacts(mode)
        agent_call_id = _complete_agent_call(mode, event_id, expected_agent, note)
        _trace_g7_hook(mode, f"{event_id}.result_record", note.strip() or f"{expected_agent} completed", event_id, f"record {expected_agent} result", {"agent": expected_agent, "agent_id": agent_call_id})
        if expected_agent == INSPECTOR_AGENT:
            _contract(mode)["inspector"] = {
                "agent_id": agent_call_id,
                "result_note": note.strip(),
                "completed_at": utc_now(),
            }
            _set_inspector_state(mode, event_id, status="complete", checkpoint_required=False)
        else:
            _contract(mode)["writer"] = {
                "agent_id": agent_call_id,
                "result_note": note.strip(),
                "completed_at": utc_now(),
            }
        next_event = _complete_current(mode, event_id)
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="completed",
            expected_agent=expected_agent,
            instruction=f"{expected_agent} completed; advance to {next_event.get('id') if next_event else 'next'}",
        )
        mode["status"] = f"g7_{expected_agent}_result_recorded"
        save_mode(ws, mode)
        return run_g7_hook_trace_until_stage_gate(ws, before_index)

    raise StateError("signal must be one of: spawn-record, agent-result")


def _g7_trace_result(mode: dict[str, Any], before_index: int, advanced: list[dict[str, Any]]) -> dict[str, Any]:
    current_event = None
    if _event(mode, "G7.COMPLETE").get("status") != "done":
        current = active_event(mode, "G7") or blocked_event(mode, "G7")
        current_event = current.get("id") if current else None
    trace = _hook_trace(mode)
    return {
        "ok": True,
        "active_event": current_event,
        "active_global_event": "G7" if current_event else None,
        "complete": _event(mode, "G7.COMPLETE").get("status") == "done",
        "advanced": advanced,
        "trace_hooks": [item.get("hook") for item in trace[before_index:] if isinstance(item, dict)],
        "events": child_events(mode, "G7"),
        "contract": _contract(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "finish": str(finish_path(mode).resolve()),
        "retrospective": str(retrospective_path(mode).resolve()),
        "inspector_report": str(inspector_report_path(mode).resolve()),
    }


def g7_status(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    _ensure_g7_event_tree(mode)
    save_mode(ws, mode)
    current = None
    if _event(mode, "G7.COMPLETE").get("status") != "done":
        current = active_event(mode, "G7") or blocked_event(mode, "G7")
    return {
        "ok": True,
        "active_event": current.get("id") if current else None,
        "complete": _event(mode, "G7.COMPLETE").get("status") == "done",
        "events": child_events(mode, "G7"),
        "contract": _contract(mode),
        "hook_trace": _hook_trace(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "finish": str(finish_path(mode).resolve()),
        "retrospective": str(retrospective_path(mode).resolve()),
        "inspector_report": str(inspector_report_path(mode).resolve()),
    }
