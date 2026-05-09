from __future__ import annotations

from pathlib import Path
from typing import Any

from .event_tree import (
    active_event,
    active_phase,
    child_events,
    event_by_id,
    mark_active_event_terminal,
    render_event_tree_markdown,
    transition_to_phase,
)
from .agent_registry import agent_spawn_contract, require_superteam_agent
from .state import (
    G1_QUESTIONS,
    G1_TERMINAL_STATUSES,
    StateError,
    is_g1_complete,
    load_mode,
    save_mode,
    validate_mode,
)
from .workspace import Workspace, utc_now, write_text


ANSWER_STATUSES = G1_TERMINAL_STATUSES
G1_SUMMARY_AGENT = require_superteam_agent("prd-writer", context="G1.SUMMARY")
INSPECTOR_AGENT = "inspector"
G1_USER_GATE_PREFIX = "G1.Q"


def _hook_trace(mode: dict[str, Any]) -> list[dict[str, Any]]:
    trace = mode.setdefault("hook_trace", [])
    if not isinstance(trace, list):
        trace = []
        mode["hook_trace"] = trace
    return trace


def _has_hook(mode: dict[str, Any], hook: str) -> bool:
    return any(isinstance(item, dict) and item.get("hook") == hook for item in _hook_trace(mode))


def _trace_g1_hook(
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


def _trace_g1_hook_once(
    mode: dict[str, Any],
    hook: str,
    trigger: str,
    event_id: str,
    instruction: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if not _has_hook(mode, hook):
        _trace_g1_hook(mode, hook, trigger, event_id, instruction, extra)


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
    instruction: str,
    expected_agent: str | None = None,
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
    missing_events: list[str] | None = None,
    findings: list[str] | None = None,
) -> None:
    missing = missing_events or []
    state = _inspector_state(mode)
    state["active_event"] = event_id
    state["status"] = status
    state["checkpoint_required"] = checkpoint_required
    state["gate_check_report"] = {
        "status": "pass" if not missing and status in {"pass", "checkpoint_pass"} else status,
        "checked_event": event_id,
        "findings": findings or [],
    }
    state["trace_coverage"] = {
        "status": "pass" if not missing else "fail",
        "missing_events": missing,
        "discrepancies": [],
    }


def _record_agent_call(
    mode: dict[str, Any],
    event_id: str,
    agent: str,
    agent_id: str,
    status: str,
    scope: str,
) -> None:
    state = _orchestrator_state(mode)
    calls = state.setdefault("agent_calls", [])
    if not isinstance(calls, list):
        calls = []
        state["agent_calls"] = calls
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
    return any(
        isinstance(item, dict) and item.get("event") == event_id and item.get("role") == agent
        for item in calls
    )


def _mark_agent_call_completed(mode: dict[str, Any], event_id: str, agent: str, note: str) -> str:
    calls = _orchestrator_state(mode).get("agent_calls") or []
    for item in reversed(calls):
        if isinstance(item, dict) and item.get("event") == event_id and item.get("role") == agent:
            item["status"] = "completed"
            item["completed_at"] = utc_now()
            item["result_note"] = note.strip()
            return str(item.get("agent_id") or "")
    raise StateError(f"{event_id} requires {agent} spawn_record before result")


def _require_inspector(mode: dict[str, Any], event_id: str, instruction: str) -> None:
    _trace_g1_hook(
        mode,
        f"{event_id}.inspector_required",
        f"expected_agent={INSPECTOR_AGENT}",
        event_id,
        instruction,
        {"expected_agent": INSPECTOR_AGENT, **agent_spawn_contract(INSPECTOR_AGENT)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=INSPECTOR_AGENT,
        instruction=f"spawn {INSPECTOR_AGENT}; OR must not impersonate Inspector",
    )
    state = _inspector_state(mode)
    state["active_event"] = event_id
    state["status"] = "waiting_for_spawn_record"
    state["checkpoint_required"] = True
    state["pending_event"] = event_id
    state["agent_id"] = None


def _record_inspector_spawn(mode: dict[str, Any], event_id: str, agent_id: str) -> None:
    call_id = agent_id.strip() or f"{INSPECTOR_AGENT}-local"
    _record_agent_call(mode, event_id, INSPECTOR_AGENT, call_id, "spawned", f"inspect {event_id} trace before advance")
    _trace_g1_hook(
        mode,
        f"{event_id}.inspector_spawn_record",
        f"agent_id={call_id}",
        event_id,
        "record inspector spawn",
        {"agent": INSPECTOR_AGENT, "agent_id": call_id, **agent_spawn_contract(INSPECTOR_AGENT)},
    )
    _trace_g1_hook(
        mode,
        f"{event_id}.inspector_wait_result",
        "waiting for inspector result",
        event_id,
        "wait for inspector result",
        {"agent": INSPECTOR_AGENT, "agent_id": call_id},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="spawned",
        spawn_status="waiting_result",
        expected_agent=INSPECTOR_AGENT,
        instruction="wait for inspector result",
    )
    state = _inspector_state(mode)
    state["active_event"] = event_id
    state["status"] = "waiting_for_agent_result"
    state["checkpoint_required"] = True
    state["pending_event"] = event_id
    state["agent_id"] = call_id


def _record_inspector_result(mode: dict[str, Any], event_id: str, note: str) -> None:
    agent_id = _mark_agent_call_completed(mode, event_id, INSPECTOR_AGENT, note)
    _trace_g1_hook(
        mode,
        f"{event_id}.inspector_result_record",
        note.strip() or "inspector completed",
        event_id,
        "record inspector result",
        {"agent": INSPECTOR_AGENT, "agent_id": agent_id},
    )
    _trace_g1_hook(
        mode,
        f"{event_id}.inspector_check",
        "inspector trace coverage pass",
        event_id,
        "Inspector agent completed trace check",
        {"agent": INSPECTOR_AGENT, "agent_id": agent_id},
    )
    _set_inspector(mode, event_id, status="pass", checkpoint_required=True)
    _inspector_state(mode)["agent_id"] = agent_id


def _ensure_g1_user_gate_waiting(mode: dict[str, Any], event_id: str) -> None:
    if event_id.startswith(G1_USER_GATE_PREFIX):
        _trace_g1_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "ask active G1 question")
        _trace_g1_hook_once(mode, f"{event_id}.hold", "waiting for user answer", event_id, "hold for user answer")
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction="ask the active G1 question; do not spawn an agent",
        )
        _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
        return

    if event_id == "G1.APPROVAL":
        _trace_g1_hook_once(mode, "G1.APPROVAL.enter", "G1.APPROVAL=active", event_id, "show G1 definition and request user approval")
        _trace_g1_hook_once(mode, "G1.APPROVAL.hold", "waiting for user approval", event_id, "hold at G1 user approval")
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction="request explicit user approval for G1",
        )
    _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)


def _trace_g1_start(mode: dict[str, Any]) -> None:
    _trace_g1_hook_once(mode, "G1.START.enter", "G1.START=active", "G1.START", "enter G1")
    try:
        next_event = mark_active_event_terminal(mode, "G1.START", "done")
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    _trace_g1_hook(
        mode,
        "G1.START.next",
        "G1.START=done",
        "G1.START",
        f"advance to {next_event.get('id') if next_event else ''}",
    )
    _set_orchestrator(
        mode,
        "G1.START",
        spawn_decision="none",
        spawn_status="not_required",
        expected_agent=None,
        instruction="complete G1.START before asking G1.Q1",
    )
    _set_inspector(mode, "G1.START", status="not_required", checkpoint_required=False)
    mode["status"] = "g1_start_done"


def _ensure_g1_summary_spawn_required(mode: dict[str, Any]) -> None:
    event_id = "G1.SUMMARY"
    _trace_g1_hook_once(mode, "G1.SUMMARY.enter", "G1.SUMMARY=active", event_id, "enter G1 summary synthesis")
    _trace_g1_hook_once(
        mode,
        "G1.SUMMARY.spawn_required",
        f"expected_agent={G1_SUMMARY_AGENT}",
        event_id,
        f"spawn {G1_SUMMARY_AGENT} to synthesize G1 project definition",
        {"expected_agent": G1_SUMMARY_AGENT, **agent_spawn_contract(G1_SUMMARY_AGENT)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=G1_SUMMARY_AGENT,
        instruction=f"spawn {G1_SUMMARY_AGENT} for G1 summary; main session must not synthesize it directly",
    )
    _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)


def project_definition_path(mode: dict[str, Any]) -> Path:
    return Path(mode["run_dir"]) / "01-project-definition.md"


def _events(mode: dict[str, Any]) -> list[dict[str, Any]]:
    return child_events(mode, "G1")


def _event(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    try:
        return event_by_id(mode, event_id)
    except KeyError as exc:
        raise StateError(str(exc)) from exc


def _active_event(mode: dict[str, Any]) -> dict[str, Any]:
    current = active_event(mode, "G1")
    if current is None:
        raise StateError("G1 must have exactly one active event before completion")
    return current


def _answer_for(mode: dict[str, Any], event_id: str) -> str:
    return str(_event(mode, event_id).get("answer") or "").strip()


def _render_project_definition(mode: dict[str, Any]) -> str:
    complete = is_g1_complete(mode)
    approval = mode.get("g1_approval") or {}
    lines = [
        "# G1 Project Definition",
        "",
        f"Status: {'approved' if complete else 'pending'}",
        "",
        render_event_tree_markdown(mode),
        "",
        "## Task",
        "",
        str(mode.get("task") or "").strip() or "SuperTeam Codex run",
        "",
        "## G1 Event Table",
        "",
        "| Event | Status | Question | Answer Ref | Next |",
        "|---|---|---|---|---|",
    ]
    for item in _events(mode):
        lines.append(
            "| {id} | {status} | {question} | {answer_ref} | {next} |".format(
                id=item.get("id", ""),
                status=item.get("status", ""),
                question=str(item.get("title", "")).replace("|", "\\|"),
                answer_ref=item.get("answer_ref") or "",
                next=item.get("next") or "",
            )
        )

    lines.extend(["", "## G1 Answers", ""])
    for event_id, question in G1_QUESTIONS:
        item = _event(mode, event_id)
        answer = str(item.get("answer") or "").strip()
        lines.extend(
            [
                f"### {event_id} {question}",
                "",
                f"- status: {item.get('status')}",
                "- answer:",
                "",
                answer if answer else "_pending_",
                "",
            ]
        )

    lines.extend(
        [
            "## SuperTeam Derived Notes",
            "",
            "- verification_strategy: derived by SuperTeam in later gates, not asked as a G1 user question",
            "- tdd_default: code-changing tasks use red -> green -> refactor unless the orchestrator records an exception",
            "- review_required: true",
            "- verify_required: true",
            f"- ui_input: {_answer_for(mode, 'G1.Q4') or 'pending'}",
            f"- data_input: {_answer_for(mode, 'G1.Q5') or 'pending'}",
            f"- integration_input: {_answer_for(mode, 'G1.Q6') or 'pending'}",
            f"- technical_constraints_input: {_answer_for(mode, 'G1.Q7') or 'pending'}",
            "",
            "## Approval",
            "",
            f"- status: {approval.get('status', 'pending')}",
            f"- approved_by: {approval.get('approved_by') or ''}",
            f"- approved_at: {approval.get('approved_at') or ''}",
            f"- note: {approval.get('note') or ''}",
            "",
        ]
    )
    return "\n".join(lines)


def write_project_definition(mode: dict[str, Any]) -> Path:
    path = project_definition_path(mode)
    write_text(path, _render_project_definition(mode))
    return path


def g1_status(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    current = None if is_g1_complete(mode) else _active_event(mode).get("id")
    return {
        "ok": True,
        "active_event": current,
        "active_global_event": active_phase(mode).get("id") if active_phase(mode) else None,
        "complete": is_g1_complete(mode),
        "events": _events(mode),
        "event_tree": mode["event_tree"],
        "hook_trace": _hook_trace(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "project_definition": str(project_definition_path(mode).resolve()),
    }


def run_g1_hook_trace_until_user_gate(ws: Workspace, before_index: int | None = None) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g1":
        raise StateError("G1 hook-trace can only run while stage=g1")
    if before_index is None:
        before_index = len(_hook_trace(mode))

    current = _active_event(mode)
    event_id = str(current.get("id"))
    if event_id == "G1.START":
        _trace_g1_start(mode)
        save_mode(ws, mode)
        write_project_definition(mode)
        return run_g1_hook_trace_until_user_gate(ws, before_index)
    if event_id.startswith(G1_USER_GATE_PREFIX) or event_id == "G1.APPROVAL":
        _ensure_g1_user_gate_waiting(mode, event_id)
        mode["status"] = f"{event_id.lower()}_waiting_for_user"
    elif event_id == "G1.SUMMARY":
        _ensure_g1_summary_spawn_required(mode)
        mode["status"] = "g1_summary_waiting_for_spawn"
    else:
        raise StateError(f"unsupported active G1 hook-trace event: {event_id}")

    save_mode(ws, mode)
    write_project_definition(mode)
    return _g1_trace_result(mode, before_index)


def apply_g1_hook_trace_signal(
    ws: Workspace,
    signal: str,
    note: str = "",
    *,
    status: str = "done",
    agent: str = G1_SUMMARY_AGENT,
    agent_id: str = "",
) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g1":
        raise StateError("G1 hook-trace signals can only be recorded while stage=g1")
    before_index = len(_hook_trace(mode))
    current = _active_event(mode)
    event_id = str(current.get("id"))

    if signal == "answer":
        if not event_id.startswith(G1_USER_GATE_PREFIX):
            raise StateError(f"active G1 event is {event_id}; cannot record answer")
        answer = note.strip()
        if not answer:
            raise StateError("answer cannot be empty")
        if status not in ANSWER_STATUSES:
            raise StateError(f"answer status must be one of {sorted(ANSWER_STATUSES)}")
        _ensure_g1_user_gate_waiting(mode, event_id)
        current["answer"] = answer
        current["answer_ref"] = f"01-project-definition.md#{event_id.lower().replace('.', '')}"
        _trace_g1_hook(mode, f"{event_id}.record", answer, event_id, "record active G1 answer")
        try:
            next_event = mark_active_event_terminal(mode, event_id, status)
        except ValueError as exc:
            raise StateError(str(exc)) from exc
        _trace_g1_hook(
            mode,
            f"{event_id}.next",
            f"{event_id}={status}",
            event_id,
            f"advance to {next_event.get('id') if next_event else ''}",
        )
        mode["status"] = f"{event_id.lower()}_{status}"
        save_mode(ws, mode)
        write_project_definition(mode)
        return run_g1_hook_trace_until_user_gate(ws, before_index)

    if signal == "spawn-record":
        if event_id != "G1.SUMMARY":
            raise StateError(f"active G1 event is {event_id}; cannot record summary spawn")
        agent_name = agent.strip() or G1_SUMMARY_AGENT
        if agent_name != G1_SUMMARY_AGENT:
            raise StateError(f"G1.SUMMARY requires agent {G1_SUMMARY_AGENT}, got {agent_name}")
        _ensure_g1_summary_spawn_required(mode)
        call_id = agent_id.strip() or f"{agent_name}-local"
        _record_agent_call(mode, event_id, agent_name, call_id, "spawned", "synthesize G1 project definition")
        _trace_g1_hook(
            mode,
            "G1.SUMMARY.spawn_record",
            f"agent_id={call_id}",
            event_id,
            f"record {agent_name} spawn",
            {"agent": agent_name, "agent_id": call_id, **agent_spawn_contract(agent_name)},
        )
        _trace_g1_hook_once(
            mode,
            "G1.SUMMARY.wait_result",
            "waiting for agent result",
            event_id,
            f"wait for {agent_name} result",
        )
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="waiting_result",
            expected_agent=G1_SUMMARY_AGENT,
            instruction=f"wait for {agent_name} result",
        )
        _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
        mode["status"] = "g1_summary_waiting_for_agent_result"
        save_mode(ws, mode)
        return _g1_trace_result(mode, before_index)

    if signal == "agent-result":
        if event_id != "G1.SUMMARY":
            raise StateError(f"active G1 event is {event_id}; cannot record summary agent result")
        calls = _orchestrator_state(mode).get("agent_calls") or []
        if not any(
            isinstance(item, dict)
            and item.get("event") == "G1.SUMMARY"
            and item.get("role") == G1_SUMMARY_AGENT
            for item in calls
        ):
            raise StateError("G1.SUMMARY requires spawn_record before agent-result")
        _mark_agent_call_completed(mode, event_id, G1_SUMMARY_AGENT, note)
        _trace_g1_hook(mode, "G1.SUMMARY.result_record", note.strip() or f"{G1_SUMMARY_AGENT} completed", event_id, f"record {G1_SUMMARY_AGENT} result")
        _require_inspector(
            mode,
            event_id,
            "spawn inspector to check G1 summary trace before user approval",
        )
        mode["status"] = "g1_summary_waiting_for_inspector_spawn"
        save_mode(ws, mode)
        write_project_definition(mode)
        return _g1_trace_result(mode, before_index)

    if signal == "inspector-spawn-record":
        if _inspector_state(mode).get("pending_event") != event_id:
            raise StateError(f"active G1 event is {event_id}; no inspector check is pending")
        agent_name = agent.strip() or INSPECTOR_AGENT
        if agent_name != INSPECTOR_AGENT:
            raise StateError(f"{event_id} requires agent {INSPECTOR_AGENT}, got {agent_name}")
        _record_inspector_spawn(mode, event_id, agent_id)
        mode["status"] = f"{event_id.lower()}_waiting_for_inspector_result"
        save_mode(ws, mode)
        return _g1_trace_result(mode, before_index)

    if signal == "inspector-result":
        if _inspector_state(mode).get("pending_event") != event_id:
            raise StateError(f"active G1 event is {event_id}; no inspector check is pending")
        if not _has_agent_call(mode, event_id, INSPECTOR_AGENT):
            raise StateError(f"{event_id} requires inspector_spawn_record before inspector-result")
        _record_inspector_result(mode, event_id, note)
        if event_id == "G1.SUMMARY":
            current["completed_at"] = utc_now()
            try:
                next_event = mark_active_event_terminal(mode, "G1.SUMMARY", "done")
            except ValueError as exc:
                raise StateError(str(exc)) from exc
            _trace_g1_hook(
                mode,
                "G1.SUMMARY.next",
                "G1.SUMMARY=done",
                event_id,
                f"advance to {next_event.get('id') if next_event else ''}",
            )
            _set_orchestrator(
                mode,
                event_id,
                spawn_decision="spawned",
                spawn_status="completed",
                expected_agent=INSPECTOR_AGENT,
                instruction="Inspector completed; request explicit user approval for G1",
            )
            _inspector_state(mode).pop("pending_event", None)
            mode["status"] = "g1_summary_ready_for_user_approval"
            save_mode(ws, mode)
            write_project_definition(mode)
            return run_g1_hook_trace_until_user_gate(ws, before_index)
        if event_id == "G1.APPROVAL":
            approval_note = str(mode.pop("pending_g1_approval_note", "") or note).strip()
            save_mode(ws, mode)
            result = approve_g1(ws, note=approval_note)
            mode = load_mode(ws)
            assert mode is not None
            _trace_g1_hook(mode, "G1.APPROVAL.next", "G1.APPROVAL=done", event_id, "advance to G1.COMPLETE")
            _trace_g1_hook(mode, "G1.COMPLETE.enter", "G1.COMPLETE=done", "G1.COMPLETE", "close G1")
            _trace_g1_hook(mode, "G1.COMPLETE.next", "G1.COMPLETE=done", "G1.COMPLETE", "advance to G2.START")
            _set_orchestrator(
                mode,
                "G1.COMPLETE",
                spawn_decision="none",
                spawn_status="not_required",
                expected_agent=None,
                instruction="G1 complete; continue to G2.START",
            )
            _inspector_state(mode).pop("pending_event", None)
            save_mode(ws, mode)
            result.update(_g1_trace_result(mode, before_index))
            return result
        raise StateError(f"unsupported G1 inspector event: {event_id}")

    if signal == "approve-g1":
        if event_id != "G1.APPROVAL":
            raise StateError(f"active G1 event is {event_id}; cannot approve G1")
        _ensure_g1_user_gate_waiting(mode, event_id)
        _trace_g1_hook(mode, "G1.APPROVAL.record", note.strip() or "user approved G1", event_id, "record explicit G1 approval")
        mode["pending_g1_approval_note"] = note.strip()
        _require_inspector(
            mode,
            event_id,
            "spawn inspector to check G1 approval before phase transition",
        )
        save_mode(ws, mode)
        return _g1_trace_result(mode, before_index)

    raise StateError("signal must be one of: answer, spawn-record, agent-result, inspector-spawn-record, inspector-result, approve-g1")


def _g1_trace_result(mode: dict[str, Any], before_index: int) -> dict[str, Any]:
    current_event = None
    if not is_g1_complete(mode):
        current = active_event(mode, "G1")
        current_event = current.get("id") if current else None
    trace = _hook_trace(mode)
    return {
        "ok": True,
        "active_event": current_event,
        "active_global_event": active_phase(mode).get("id") if active_phase(mode) else None,
        "complete": is_g1_complete(mode),
        "trace": trace[before_index:],
        "trace_hooks": [item.get("hook") for item in trace[before_index:]],
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "project_definition": str(project_definition_path(mode).resolve()),
    }


def record_g1_answer(ws: Workspace, answer: str, status: str = "done") -> dict[str, Any]:
    if status not in ANSWER_STATUSES:
        raise StateError(f"answer status must be one of {sorted(ANSWER_STATUSES)}")
    answer = answer.strip()
    if not answer:
        raise StateError("answer cannot be empty")
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g1":
        raise StateError("G1 answers can only be recorded while stage=g1")
    current = _active_event(mode)
    current_id = str(current.get("id"))
    if current_id == "G1.START":
        _trace_g1_start(mode)
        current = _active_event(mode)
        current_id = str(current.get("id"))
    if not current_id.startswith("G1.Q"):
        raise StateError(f"active G1 event is {current_id}; use the matching G1 command instead")
    current["answer"] = answer
    current["answer_ref"] = f"01-project-definition.md#{current_id.lower().replace('.', '')}"
    try:
        mark_active_event_terminal(mode, current_id, status)
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    next_event = active_event(mode, "G1")
    mode["status"] = f"{current_id.lower()}_{status}"
    save_mode(ws, mode)
    path = write_project_definition(mode)
    return {
        "ok": True,
        "event": current_id,
        "status": status,
        "next_event": next_event.get("id") if next_event else None,
        "project_definition": str(path.resolve()),
    }


def complete_g1_summary(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g1":
        raise StateError("G1 summary can only be completed while stage=g1")
    for event_id, _question in G1_QUESTIONS:
        status = _event(mode, event_id).get("status")
        if status not in G1_TERMINAL_STATUSES:
            raise StateError(f"{event_id} must be answered/deferred/not_applicable before G1.SUMMARY")
    current = _active_event(mode)
    if current.get("id") != "G1.SUMMARY":
        raise StateError(f"active G1 event is {current.get('id')}; cannot complete G1.SUMMARY")
    current["completed_at"] = utc_now()
    try:
        mark_active_event_terminal(mode, "G1.SUMMARY", "done")
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    next_event = active_event(mode, "G1")
    mode["status"] = "g1_summary_ready_for_user_approval"
    save_mode(ws, mode)
    path = write_project_definition(mode)
    return {
        "ok": True,
        "event": "G1.SUMMARY",
        "status": "done",
        "next_event": next_event.get("id") if next_event else None,
        "project_definition": str(path.resolve()),
    }


def approve_g1(ws: Workspace, approved_by: str = "user", note: str = "") -> dict[str, Any]:
    if approved_by != "user":
        raise StateError("G1 approval must be approved_by='user'")
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g1":
        raise StateError("G1 approval can only be recorded while stage=g1")
    if _event(mode, "G1.SUMMARY").get("status") != "done":
        raise StateError("G1.SUMMARY must be done before user approval")
    current = _active_event(mode)
    if current.get("id") != "G1.APPROVAL":
        raise StateError(f"active G1 event is {current.get('id')}; cannot approve G1")
    now = utc_now()
    current["answer_ref"] = "01-project-definition.md#approval"
    current["approved_at"] = now
    try:
        mark_active_event_terminal(mode, "G1.APPROVAL", "done")
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    complete = _event(mode, "G1.COMPLETE")
    complete["status"] = "done"
    complete["completed_at"] = now
    mode["g1_approval"] = {
        "status": "approved",
        "approved_by": approved_by,
        "approved_at": now,
        "note": note.strip(),
    }
    try:
        transition_to_phase(mode, "G2")
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    mode["status"] = "g2_ready_for_design"
    save_mode(ws, mode)
    path = write_project_definition(mode)
    return {
        "ok": True,
        "event": "G1.COMPLETE",
        "status": "done",
        "next_global_event": "G2",
        "next_event": active_event(mode, "G2").get("id") if active_event(mode, "G2") else None,
        "project_definition": str(path.resolve()),
    }
