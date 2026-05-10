from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .agent_registry import agent_reuse_hook_instruction, agent_spawn_contract, register_agent_call, require_superteam_agent, validate_spawn_policies
from .event_tree import (
    G2_EVENT_IDS,
    active_event,
    blocked_event,
    child_events,
    event_by_id,
    mark_active_event_terminal,
    render_event_tree_markdown,
    set_event_status,
    transition_to_phase,
)
from . import g3 as g3_design
from .state import StateError, is_g1_complete, is_g2_complete, load_mode, save_mode, validate_mode
from .workspace import Workspace, file_sha256, read_json, utc_now, write_text


PENCIL_SKIP_EVENTS = [
    "G2.DRAFT_UI_DESIGN_PLAN",
    "G2.APPROVE_UI_DESIGN_PLAN",
    "G2.CREATE_PENCIL_PROJECT",
    "G2.OPEN_PENCIL",
    "G2.DESIGN_PENCIL_STEPS",
    "G2.EXTRACT_PENCIL_FRAMES",
    "G2.MAP_FEATURE_TO_PENCIL_FRAME",
    "G2.CHECK_FEATURE_UI_MAP",
    "G2.MAP_PENCIL_TO_CODE_TARGETS",
    "G2.EXTRACT_LAYOUT_SPEC",
    "G2.EXTRACT_DESIGN_TOKENS",
    "G2.MAP_INTERACTION_STATES",
    "G2.WRITE_VISUAL_ACCEPTANCE",
    "G2.CHECK_UI_IMPLEMENTATION_CONTRACT",
    "G2.WRITE_PENCIL_CONTRACT_MAP",
    "G2.CHECK_PENCIL_CONTRACT_MAP",
    "G2.DELIVER_PENCIL_DESIGN",
]

PENCIL_INTERACTION_EVENTS = [
    "G2.DRAFT_UI_DESIGN_PLAN",
    "G2.APPROVE_UI_DESIGN_PLAN",
    "G2.CREATE_PENCIL_PROJECT",
    "G2.OPEN_PENCIL",
    "G2.DESIGN_PENCIL_STEPS",
]

PENCIL_VALIDATION_EVENTS = [
    "G2.EXTRACT_PENCIL_FRAMES",
    "G2.MAP_FEATURE_TO_PENCIL_FRAME",
    "G2.CHECK_FEATURE_UI_MAP",
    "G2.MAP_PENCIL_TO_CODE_TARGETS",
    "G2.EXTRACT_LAYOUT_SPEC",
    "G2.EXTRACT_DESIGN_TOKENS",
    "G2.MAP_INTERACTION_STATES",
    "G2.WRITE_VISUAL_ACCEPTANCE",
    "G2.CHECK_UI_IMPLEMENTATION_CONTRACT",
    "G2.WRITE_PENCIL_CONTRACT_MAP",
    "G2.CHECK_PENCIL_CONTRACT_MAP",
    "G2.DELIVER_PENCIL_DESIGN",
]

G2_USER_GATE_EVENTS = {
    "G2.APPROVE_UI_DESIGN_PLAN",
    "G2.DESIGN_PENCIL_STEPS",
    "G2.USER_APPROVAL",
}

G2_DESIGN_ITEM_GROUP_ID = "G2.DESIGN_PENCIL_STEPS.ITEMS"
G2_DESIGN_ITEM_PREFIX = "G2.DESIGN_PENCIL_STEPS.ITEM_"
INSPECTOR_AGENT = "inspector"
G2_PENCIL_DESIGN_AGENT = require_superteam_agent("designer", context="G2.DESIGN_PENCIL_STEPS")
G2_SPAWN_POLICIES: dict[str, dict[str, str]] = {
    "G2.DRAFT_UI_DESIGN_PLAN": {
        "agent": "designer",
        "scope": "draft the G2 UI design plan from the approved G1 definition",
    },
    "G2.REVIEW_SOURCE_PACK": {
        "agent": "researcher",
        "scope": "review source-manifest.json before G2 design contract drafting",
    },
    "G2.DRAFT_DESIGN_CONTRACT": {
        "agent": "architect",
        "scope": "draft the G2 design contract from source, Pencil, and G1 evidence",
    },
    "G2.WRITE_DESIGN_ARTIFACT": {
        "agent": "architect",
        "scope": "write the derived 02-design.md artifact from the G2 contract",
    },
}
validate_spawn_policies(G2_SPAWN_POLICIES, context="G2_SPAWN_POLICIES")


def design_path(mode: dict[str, Any]) -> Path:
    return Path(mode["run_dir"]) / "02-design.md"


def _path_in_run(mode: dict[str, Any], name: str) -> Path:
    return Path(mode["run_dir"]) / name


def _event(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    try:
        return event_by_id(mode, event_id)
    except KeyError as exc:
        raise StateError(str(exc)) from exc


def _event_tree_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    tree = mode.setdefault("event_tree", [])
    if not isinstance(tree, list):
        raise StateError("mode.event_tree is missing or invalid")
    return tree


def _g2_design_item_id(index: int) -> str:
    return f"{G2_DESIGN_ITEM_PREFIX}{index:03d}"


def _g2_design_item_group_node() -> dict[str, Any]:
    return {
        "id": G2_DESIGN_ITEM_GROUP_ID,
        "parent": "G2.DESIGN_PENCIL_STEPS",
        "phase": "G2",
        "kind": "design_item_group",
        "status": "pending",
        "title": "UI design items pending approved G2 design plan",
        "requires": [],
        "next": None,
        "authority": ["mode.json:g2_contract.ui_plan", "user_prompt", "*.pen"],
        "artifact": "02-design.md",
        "hook_policy": "materialize_from_approved_ui_plan",
        "requires_answer": False,
        "answer": "",
        "answer_ref": None,
    }


def _ensure_g2_design_item_group(mode: dict[str, Any]) -> bool:
    if any(item.get("id") == G2_DESIGN_ITEM_GROUP_ID for item in _event_tree_items(mode) if isinstance(item, dict)):
        return False
    _event_tree_items(mode).append(_g2_design_item_group_node())
    return True


def _g2_design_item_nodes(mode: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [
        item
        for item in _event_tree_items(mode)
        if isinstance(item, dict)
        and item.get("parent") == G2_DESIGN_ITEM_GROUP_ID
        and item.get("kind") == "design_item"
    ]
    return sorted(nodes, key=lambda item: int(item.get("design_index") or 0))


def _g2_design_item_node(title: str, index: int, total: int) -> dict[str, Any]:
    event_id = _g2_design_item_id(index)
    next_event = _g2_design_item_id(index + 1) if index < total else None
    return {
        "id": event_id,
        "parent": G2_DESIGN_ITEM_GROUP_ID,
        "phase": "G2",
        "kind": "design_item",
        "status": "pending",
        "title": title,
        "requires": [],
        "next": next_event,
        "authority": ["mode.json:g2_contract.ui_plan", "user_prompt", "*.pen"],
        "artifact": "02-design.md",
        "hook_policy": "user_steered_pencil_design_item",
        "requires_answer": True,
        "answer": "",
        "answer_ref": None,
        "design_index": index,
    }


def _materialize_g2_design_item_tree(mode: dict[str, Any]) -> bool:
    changed = _ensure_g2_design_item_group(mode)
    ui_plan = [str(item).strip() for item in (_contract(mode).get("ui_plan") or []) if str(item).strip()]
    if not ui_plan:
        return changed

    existing = _g2_design_item_nodes(mode)
    existing_signature = [(item.get("id"), item.get("title")) for item in existing]
    expected_signature = [(_g2_design_item_id(index), item) for index, item in enumerate(ui_plan, start=1)]
    if existing_signature == expected_signature:
        return changed

    tree = _event_tree_items(mode)
    mode["event_tree"] = [
        item
        for item in tree
        if not (
            isinstance(item, dict)
            and item.get("parent") == G2_DESIGN_ITEM_GROUP_ID
            and item.get("kind") == "design_item"
        )
    ]
    for index, item in enumerate(ui_plan, start=1):
        mode["event_tree"].append(_g2_design_item_node(item, index, len(ui_plan)))
    group = _event(mode, G2_DESIGN_ITEM_GROUP_ID)
    group["title"] = "UI design items from approved G2 design plan"
    group["answer_ref"] = "mode.json:g2_contract.ui_plan"
    return True


def _activate_g2_design_item_tree(mode: dict[str, Any]) -> bool:
    changed = _materialize_g2_design_item_tree(mode)
    items = _g2_design_item_nodes(mode)
    group = _event(mode, G2_DESIGN_ITEM_GROUP_ID)
    steps = (_contract(mode).get("pencil_design") or {}).get("steps") or []
    if not items:
        if group.get("status") != "active":
            group["status"] = "active"
            changed = True
        return changed

    active_index = min(len(steps) + 1, len(items))
    for item in items:
        design_index = int(item.get("design_index") or 0)
        next_status = "done" if design_index <= len(steps) else "active" if design_index == active_index else "pending"
        if item.get("status") != next_status:
            item["status"] = next_status
            changed = True
    if group.get("status") != "active":
        group["status"] = "active"
        changed = True
    return changed


def _complete_g2_design_item_tree(mode: dict[str, Any]) -> bool:
    changed = _materialize_g2_design_item_tree(mode)
    group = _event(mode, G2_DESIGN_ITEM_GROUP_ID)
    if group.get("status") != "done":
        group["status"] = "done"
        changed = True
    for item in _g2_design_item_nodes(mode):
        if item.get("status") != "done":
            item["status"] = "done"
            changed = True
    return changed


def _mark_g2_design_item_recorded(mode: dict[str, Any], step_number: int, note: str) -> None:
    event_id = _g2_design_item_id(step_number)
    try:
        item = _event(mode, event_id)
    except StateError:
        return
    item["status"] = "done"
    item["answer"] = note
    item["answer_ref"] = f"mode.json:g2_contract.pencil_design.steps[{step_number - 1}]"
    item["completed_at"] = utc_now()


def _active_g2_event(mode: dict[str, Any]) -> dict[str, Any]:
    current = active_event(mode, "G2")
    if current is None:
        blocked = blocked_event(mode, "G2")
        if blocked is not None:
            raise StateError(f"G2 is blocked at {blocked.get('id')}: {blocked.get('blocked_reason', '')}")
        raise StateError("G2 must have exactly one active event before completion")
    return current


def _contract(mode: dict[str, Any]) -> dict[str, Any]:
    contract = mode.setdefault("g2_contract", {})
    contract.setdefault("status", "pending")
    contract.setdefault("ui_authority", "pencil")
    contract.setdefault("project_definition", None)
    contract.setdefault("project_definition_contract", None)
    contract.setdefault("source_review", None)
    contract.setdefault("ui", None)
    contract.setdefault("ui_plan", [])
    contract.setdefault("pencil_design", {"steps": [], "deliverables": []})
    contract.setdefault("deliverables", {})
    contract.setdefault("design_decisions", [])
    return contract


def _hook_trace(mode: dict[str, Any]) -> list[dict[str, Any]]:
    trace = mode.setdefault("hook_trace", [])
    if not isinstance(trace, list):
        trace = []
        mode["hook_trace"] = trace
    return trace


def _has_hook(mode: dict[str, Any], hook: str) -> bool:
    return any(isinstance(item, dict) and item.get("hook") == hook for item in _hook_trace(mode))


def _trace_g2_hook(
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


def _trace_g2_hook_once(
    mode: dict[str, Any],
    hook: str,
    trigger: str,
    event_id: str,
    instruction: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if not _has_hook(mode, hook):
        _trace_g2_hook(mode, hook, trigger, event_id, instruction, extra)


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
    state["hook_instruction"] = agent_reuse_hook_instruction(expected_agent, instruction) if expected_agent else instruction


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
) -> str:
    call = register_agent_call(mode, event_id, agent, agent_id, status, scope)
    return str(call.get("agent_id") or "")


def _mark_agent_call_completed(mode: dict[str, Any], event_id: str, agent: str, note: str) -> str:
    calls = _orchestrator_state(mode).get("agent_calls") or []
    for item in reversed(calls):
        if isinstance(item, dict) and item.get("event") == event_id and item.get("role") == agent:
            item["status"] = "completed"
            item["completed_at"] = utc_now()
            item["result_note"] = note.strip()
            return str(item.get("agent_id") or "")
    raise StateError(f"{event_id} requires {agent} spawn_record before result")


def _has_agent_call(mode: dict[str, Any], event_id: str, agent: str) -> bool:
    calls = _orchestrator_state(mode).get("agent_calls") or []
    return any(
        isinstance(item, dict) and item.get("event") == event_id and item.get("role") == agent
        for item in calls
    )


def _require_g2_inspector(mode: dict[str, Any], event_id: str, instruction: str) -> None:
    _trace_g2_hook(
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


def _record_g2_inspector_spawn(mode: dict[str, Any], event_id: str, agent_id: str) -> None:
    call_id = _record_agent_call(
        mode,
        event_id,
        INSPECTOR_AGENT,
        agent_id.strip() or f"{INSPECTOR_AGENT}-local",
        "spawned",
        f"inspect {event_id} trace before advance",
    )
    _trace_g2_hook(
        mode,
        f"{event_id}.inspector_spawn_record",
        f"agent_id={call_id}",
        event_id,
        "record inspector spawn",
        {"agent": INSPECTOR_AGENT, "agent_id": call_id, **agent_spawn_contract(INSPECTOR_AGENT)},
    )
    _trace_g2_hook(
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


def _record_g2_inspector_result(mode: dict[str, Any], event_id: str, note: str) -> None:
    agent_id = _mark_agent_call_completed(mode, event_id, INSPECTOR_AGENT, note)
    _trace_g2_hook(
        mode,
        f"{event_id}.inspector_result_record",
        note.strip() or "inspector completed",
        event_id,
        "record inspector result",
        {"agent": INSPECTOR_AGENT, "agent_id": agent_id},
    )
    _trace_g2_hook(
        mode,
        f"{event_id}.inspector_check",
        "inspector trace coverage pass",
        event_id,
        "Inspector agent completed trace check",
        {"agent": INSPECTOR_AGENT, "agent_id": agent_id},
    )
    _set_inspector(mode, event_id, status="pass", checkpoint_required=True)
    _inspector_state(mode)["agent_id"] = agent_id


def _trace_g2_transition(
    mode: dict[str, Any],
    event_id: str,
    next_event: dict[str, Any] | None,
    note: str = "",
) -> None:
    _trace_g2_hook(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter active G2 event")
    _trace_g2_hook(
        mode,
        f"{event_id}.record",
        note.strip() or "runtime recorded event result",
        event_id,
        "record active G2 event result",
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="none",
        spawn_status="not_required",
        expected_agent=None,
        instruction=f"complete {event_id} without spawning an agent",
    )
    _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
    if next_event is not None:
        next_id = str(next_event.get("id") or "")
        if next_id == "G2.DESIGN_PENCIL_STEPS":
            _activate_g2_design_item_tree(mode)
        _trace_g2_hook(
            mode,
            f"{event_id}.next",
            f"{event_id}=done",
            event_id,
            f"advance to {next_id}",
        )
        if next_id in G2_USER_GATE_EVENTS and not _has_hook(mode, f"{next_id}.enter"):
            _trace_g2_hook_once(
                mode,
                f"{next_id}.enter",
                f"{next_id}=active",
                next_id,
                f"enter user interaction gate {next_id}",
            )


def _ensure_g2_spawn_required(mode: dict[str, Any], event_id: str) -> None:
    policy = G2_SPAWN_POLICIES[event_id]
    agent = policy["agent"]
    _trace_g2_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter active G2 event")
    _trace_g2_hook_once(
        mode,
        f"{event_id}.spawn_required",
        f"expected_agent={agent}",
        event_id,
        f"spawn {agent} for {event_id}",
        {"expected_agent": agent, "scope": policy["scope"], **agent_spawn_contract(agent)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=agent,
        instruction=f"spawn {agent}; main session must not complete {event_id} directly",
    )
    _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)


def _ensure_g2_pencil_designer_required(mode: dict[str, Any]) -> None:
    event_id = "G2.DESIGN_PENCIL_STEPS"
    agent = G2_PENCIL_DESIGN_AGENT
    _trace_g2_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter Pencil strong-interaction design gate")
    _trace_g2_hook_once(
        mode,
        f"{event_id}.spawn_required",
        f"expected_agent={agent}",
        event_id,
        f"spawn {agent} before user-steered Pencil design",
        {"expected_agent": agent, "scope": "own UI intent while the user steers Pencil design", **agent_spawn_contract(agent)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=agent,
        instruction=f"spawn {agent}; then hold for user-steered Pencil design",
    )
    _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)


def _trace_g2_agent_result_transition(
    mode: dict[str, Any],
    event_id: str,
    next_event: dict[str, Any] | None,
    note: str,
) -> None:
    policy = G2_SPAWN_POLICIES[event_id]
    agent = policy["agent"]
    _mark_agent_call_completed(mode, event_id, agent, note)
    _trace_g2_hook(
        mode,
        f"{event_id}.result_record",
        note.strip() or f"{agent} completed",
        event_id,
        f"record {agent} result",
        {"agent": agent},
    )
    _require_g2_inspector(mode, event_id, f"spawn inspector to check {event_id} before next")


def _ensure_g2_user_gate_waiting(mode: dict[str, Any], event_id: str) -> None:
    if event_id == "G2.APPROVE_UI_DESIGN_PLAN":
        _trace_g2_hook_once(
            mode,
            "G2.APPROVE_UI_DESIGN_PLAN.enter",
            "G2.APPROVE_UI_DESIGN_PLAN=active",
            event_id,
            "show UI design plan and wait for user approval",
        )
        _trace_g2_hook_once(
            mode,
            "G2.APPROVE_UI_DESIGN_PLAN.hold",
            "waiting for user approval",
            event_id,
            "hold at G2 UI design plan approval",
        )
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction="show the G2 UI design plan and wait for explicit user approval",
        )
        _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
        return

    if event_id == "G2.DESIGN_PENCIL_STEPS":
        _activate_g2_design_item_tree(mode)
        contract = _contract(mode)
        ui_plan = contract.get("ui_plan") or []
        steps = (contract.get("pencil_design") or {}).get("steps") or []
        step_number = len(steps) + 1
        plan_item = ui_plan[len(steps)] if ui_plan and len(steps) < len(ui_plan) else ""
        _trace_g2_hook_once(
            mode,
            "G2.DESIGN_PENCIL_STEPS.enter",
            "G2.DESIGN_PENCIL_STEPS=active",
            event_id,
            "enter Pencil strong-interaction design gate",
        )
        if plan_item:
            _trace_g2_hook_once(
                mode,
                f"G2.DESIGN_PENCIL_STEPS.item{step_number}.enter",
                f"plan_item={plan_item}",
                event_id,
                f"show Pencil design item {step_number}",
                {"plan_item": plan_item, "step_number": step_number},
            )
            _trace_g2_hook_once(
                mode,
                f"G2.DESIGN_PENCIL_STEPS.item{step_number}.hold",
                "waiting for user-steered Pencil design",
                event_id,
                f"hold at Pencil design item {step_number}",
                {"plan_item": plan_item, "step_number": step_number},
            )
        else:
            _trace_g2_hook_once(
                mode,
                "G2.DESIGN_PENCIL_STEPS.hold",
                "waiting for design-done signal",
                event_id,
                "hold until user gives the Pencil design-done signal",
            )
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction="hold for user-steered Pencil design; do not replace Pencil interaction with AI output",
        )
        _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
        return

    if event_id == "G2.USER_APPROVAL":
        _trace_g2_hook_once(
            mode,
            "G2.USER_APPROVAL.enter",
            "G2.USER_APPROVAL=active",
            event_id,
            "show G2 design artifact and wait for user approval",
        )
        _trace_g2_hook_once(
            mode,
            "G2.USER_APPROVAL.hold",
            "waiting for user approval",
            event_id,
            "hold at final G2 approval",
        )
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction="show 02-design.md and wait for explicit G2 approval",
        )
        _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)


def _g1_answer(mode: dict[str, Any], event_id: str) -> str:
    return str(_event(mode, event_id).get("answer") or "").strip()


def _ui_required(mode: dict[str, Any]) -> bool:
    q4 = _event(mode, "G1.Q4")
    if q4.get("status") == "not_applicable":
        return False
    answer = _g1_answer(mode, "G1.Q4").lower()
    negative_tokens = ["不需要", "无需", "无 ui", "无ui", "no ui", "no user interface", "cli", "后台工具"]
    return not any(token in answer for token in negative_tokens)


def _complete_current(mode: dict[str, Any], event_id: str) -> dict[str, Any] | None:
    try:
        return mark_active_event_terminal(mode, event_id, "done")
    except ValueError as exc:
        raise StateError(str(exc)) from exc


def _block_current(mode: dict[str, Any], current: dict[str, Any], reason: str) -> None:
    current["status"] = "blocked"
    current["blocked_reason"] = reason
    current["blocked_at"] = utc_now()
    mode["status"] = f"{str(current.get('id')).lower()}_blocked"


def _pencil_files_from_manifest(mode: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = _load_manifest(mode)
    return [item for item in manifest.get("files", []) if item.get("kind") == "pencil"]


def _discover_pencil_files(ws: Workspace) -> list[Path]:
    files: list[Path] = []
    for path in (ws.root / "pencil").rglob("*.pen") if (ws.root / "pencil").exists() else []:
        if ".superteam_codex" not in path.parts:
            files.append(path.resolve())
    if files:
        return sorted(files, key=lambda item: str(item).lower())
    for path in ws.root.rglob("*.pen"):
        if ".superteam_codex" not in path.parts:
            files.append(path.resolve())
    return sorted(files, key=lambda item: str(item).lower())


def _default_pencil_path(ws: Workspace, mode: dict[str, Any]) -> Path:
    slug = str(mode.get("active_task_slug") or "project").strip() or "project"
    return ws.root / "pencil" / slug / f"{slug}.pen"


def _ensure_pencil_project(ws: Workspace, mode: dict[str, Any]) -> Path:
    existing = _discover_pencil_files(ws)
    if existing:
        return existing[0]
    path = _default_pencil_path(ws, mode)
    write_text(
        path,
        '{\n'
        '  "version": "2.11",\n'
        '  "children": []\n'
        '}\n',
    )
    return path


def _split_design_plan_items(text: str) -> list[str]:
    normalized = re.sub(r"\s+\band\b\s+", ",", text.strip(), flags=re.IGNORECASE)
    parts = re.split(r"[,;\uFF0C\uFF1B\u3001\n]+", normalized)
    return [part.strip(" .\u3002") for part in parts if part.strip(" .\u3002")]


def _default_ui_plan(mode: dict[str, Any]) -> list[str]:
    features = _split_design_plan_items(_g1_answer(mode, "G1.Q3"))
    return features or ["Login", "Game library", "Quest device list"]


def _ui_plan_from_agent_note(note: str) -> list[str]:
    text = note.strip()
    if not text:
        return []
    marker = "UI_PLAN_JSON:"
    if marker in text:
        payload = text.split(marker, 1)[1].strip()
        first_line = payload.splitlines()[0].strip()
        try:
            parsed = json.loads(first_line)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:[-*]\s*)?(S\d+[-.、\s].+)$", stripped, flags=re.IGNORECASE)
        if match:
            items.append(match.group(1).strip())
    return items


def _load_manifest(mode: dict[str, Any]) -> dict[str, Any]:
    return read_json(_path_in_run(mode, "source-manifest.json"), {}) or {}


def _load_inventory(mode: dict[str, Any]) -> dict[str, Any]:
    return read_json(_path_in_run(mode, "frame-inventory.json"), {}) or {}


def _load_mapping(mode: dict[str, Any]) -> dict[str, Any]:
    return read_json(_path_in_run(mode, "feature-ui-map.json"), {}) or {}


def _write_design(mode: dict[str, Any]) -> Path:
    contract = _contract(mode)
    approval = mode.get("g2_approval") or {}
    ui = contract.get("ui") or {}
    source_review = contract.get("source_review") or {}
    project_definition = contract.get("project_definition") or {}
    lines = [
        "# G2 Design",
        "",
        f"Status: {approval.get('status') if approval.get('status') == 'approved' else contract.get('status', 'pending')}",
        "",
        render_event_tree_markdown(mode),
        "",
        "## Design Authority",
        "",
        "- UI authority: Pencil `.pen` file and real frame ids",
        "- `02-design.md` is a derived explanation, not the UI source of truth",
        f"- project_definition: {project_definition.get('path') or ''}",
        f"- project_definition_sha256: {project_definition.get('sha256') or ''}",
        "",
        "## Source Review",
        "",
        f"- status: {source_review.get('status', 'pending')}",
        f"- reviewed_at: {source_review.get('reviewed_at', '')}",
        "",
        "| Source | Kind | SHA256 |",
        "|---|---|---|",
    ]
    for item in source_review.get("files", [])[:200]:
        lines.append(f"| {item.get('path', '')} | {item.get('kind', '')} | {item.get('sha256', '')} |")

    lines.extend(
        [
            "",
            "## Approved UI Design Plan",
            "",
        ]
    )
    ui_plan = contract.get("ui_plan") or []
    if ui_plan:
        for index, item in enumerate(ui_plan, start=1):
            lines.append(f"{index}. {item}")
    else:
        lines.append("- pending")

    lines.extend(
        [
            "",
            "## Pencil UI Contract",
            "",
            f"- ui_required: {ui.get('required')}",
            f"- authority: {ui.get('authority', 'pencil')}",
            f"- feature_ui_map_status: {ui.get('feature_ui_map_status', '')}",
            "",
            "### Pencil Files",
            "",
        ]
    )
    for item in ui.get("pencil_files", []):
        lines.append(f"- `{item.get('path')}` sha256={item.get('sha256')}")
    if not ui.get("pencil_files"):
        lines.append("- NO_UI or pending")

    lines.extend(["", "### Frames", ""])
    for frame in ui.get("frames", [])[:200]:
        lines.append(f"- `{frame.get('id')}` - {frame.get('name')} ({frame.get('source_file')})")
    if not ui.get("frames"):
        lines.append("- NO_UI or pending")

    lines.extend(["", "### Strong Interaction Steps", ""])
    pencil_design = contract.get("pencil_design") or {}
    steps = pencil_design.get("steps") or []
    if steps:
        for index, step in enumerate(steps, start=1):
            lines.append(f"{index}. {step.get('note', '')}")
    else:
        lines.append("- pending")

    lines.extend(["", "### Feature To Frame References", ""])
    references = ui.get("references") or {}
    if references:
        for frame_id, hits in sorted(references.items()):
            lines.append(f"- `{frame_id}`")
            for hit in hits[:10]:
                lines.append(f"  - `{hit.get('file')}:{hit.get('line')}` {hit.get('snippet')}")
    else:
        lines.append("- NO_UI or pending")

    lines.extend(
        [
            "",
            "## Behavior Contracts",
            "",
            f"- goal: {_g1_answer(mode, 'G1.Q1')}",
            f"- users_roles: {_g1_answer(mode, 'G1.Q2')}",
            f"- features: {_g1_answer(mode, 'G1.Q3')}",
            f"- data: {_g1_answer(mode, 'G1.Q5')}",
            f"- integrations: {_g1_answer(mode, 'G1.Q6')}",
            f"- technical_constraints: {_g1_answer(mode, 'G1.Q7')}",
            "",
            "## Chosen Approach",
            "",
            "- G2 owns Pencil screenshots, visual acceptance, and `pencil-contract-map.json` as design authorities.",
            "- G3 tasks must cite source files, Pencil frame ids, and G2 design contract refs, or `NO_UI` for non-UI work.",
            "- G4 executor must read the cited Pencil contract and reference screenshot before UI code changes.",
            "- G5/G6 must keep their normal review/verification gates and add UI fidelity review against G2 reference screenshots.",
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
    path = design_path(mode)
    write_text(path, "\n".join(lines))
    return path


def write_design(mode: dict[str, Any]) -> Path:
    return _write_design(mode)


def g2_status(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    _ensure_g2_design_item_group(mode)
    current = None
    if not is_g2_complete(mode):
        current_event = active_event(mode, "G2") or blocked_event(mode, "G2")
        current = current_event.get("id") if current_event else None
    return {
        "ok": True,
        "active_event": current,
        "complete": is_g2_complete(mode),
        "events": child_events(mode, "G2"),
        "event_tree": mode["event_tree"],
        "contract": _contract(mode),
        "hook_trace": _hook_trace(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "design": str(design_path(mode).resolve()),
    }


def run_g2_hook_trace_until_user_gate(ws: Workspace, before_index: int | None = None) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g2":
        raise StateError("G2 hook-trace can only run while stage=g2")
    _ensure_g2_design_item_group(mode)
    if before_index is None:
        before_index = len(_hook_trace(mode))

    advanced: list[dict[str, Any]] = []
    while True:
        current = _active_g2_event(mode)
        event_id = str(current.get("id"))
        if event_id == "G2.DESIGN_PENCIL_STEPS" and not _has_agent_call(mode, event_id, G2_PENCIL_DESIGN_AGENT):
            _activate_g2_design_item_tree(mode)
            _ensure_g2_pencil_designer_required(mode)
            mode["status"] = "g2_design_pencil_steps_waiting_for_designer_spawn"
            save_mode(ws, mode)
            if design_path(mode).exists():
                _write_design(mode)
            return _g2_trace_result(mode, before_index, advanced)
        if event_id in G2_USER_GATE_EVENTS:
            _ensure_g2_user_gate_waiting(mode, event_id)
            mode["status"] = f"{event_id.lower()}_waiting_for_user"
            save_mode(ws, mode)
            if design_path(mode).exists():
                _write_design(mode)
            return _g2_trace_result(mode, before_index, advanced)

        if event_id in G2_SPAWN_POLICIES:
            _ensure_g2_spawn_required(mode, event_id)
            mode["status"] = f"{event_id.lower()}_waiting_for_spawn"
            save_mode(ws, mode)
            if design_path(mode).exists():
                _write_design(mode)
            return _g2_trace_result(mode, before_index, advanced)

        result = advance_g2(ws)
        advanced.append({"event": result["event"], "next_event": result.get("next_event")})
        mode = load_mode(ws)
        errors = validate_mode(mode)
        if errors:
            raise StateError("; ".join(errors))
        assert mode is not None


def apply_g2_hook_trace_signal(
    ws: Workspace,
    signal: str,
    note: str = "",
    *,
    complete: bool = False,
    agent: str = "",
    agent_id: str = "",
) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    before_index = len(_hook_trace(mode))
    current = _active_g2_event(mode)
    event_id = str(current.get("id"))

    if signal == "spawn-record":
        if event_id == "G2.DESIGN_PENCIL_STEPS":
            expected_agent = G2_PENCIL_DESIGN_AGENT
            agent_name = agent.strip() or expected_agent
            if agent_name != expected_agent:
                raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")
            _ensure_g2_pencil_designer_required(mode)
            call_id = _record_agent_call(
                mode,
                event_id,
                agent_name,
                agent_id.strip() or f"{agent_name}-local",
                "spawned",
                "own UI intent while the user steers Pencil design",
            )
            _trace_g2_hook(
                mode,
                f"{event_id}.spawn_record",
                f"agent_id={call_id}",
                event_id,
                f"record {agent_name} spawn",
                {"agent": agent_name, "agent_id": call_id, **agent_spawn_contract(agent_name)},
            )
            _trace_g2_hook_once(
                mode,
                f"{event_id}.hold",
                "waiting for user-steered Pencil design",
                event_id,
                "hold for user-steered Pencil design with designer attached",
            )
            _set_orchestrator(
                mode,
                event_id,
                spawn_decision="spawned",
                spawn_status="waiting_user",
                expected_agent=expected_agent,
                instruction="hold for user-steered Pencil design; designer is attached",
            )
            _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
            mode["status"] = "g2_pencil_design_steps_waiting_for_user"
            save_mode(ws, mode)
            return run_g2_hook_trace_until_user_gate(ws, before_index)
        if event_id not in G2_SPAWN_POLICIES:
            raise StateError(f"active G2 event is {event_id}; cannot record spawn")
        policy = G2_SPAWN_POLICIES[event_id]
        expected_agent = policy["agent"]
        agent_name = agent.strip() or expected_agent
        if agent_name != expected_agent:
            raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")
        _ensure_g2_spawn_required(mode, event_id)
        call_id = _record_agent_call(
            mode,
            event_id,
            agent_name,
            agent_id.strip() or f"{agent_name}-local",
            "spawned",
            policy["scope"],
        )
        _trace_g2_hook(
            mode,
            f"{event_id}.spawn_record",
            f"agent_id={call_id}",
            event_id,
            f"record {agent_name} spawn",
            {"agent": agent_name, "agent_id": call_id, **agent_spawn_contract(agent_name)},
        )
        _trace_g2_hook_once(
            mode,
            f"{event_id}.wait_result",
            "waiting for agent result",
            event_id,
            f"wait for {agent_name} result",
        )
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="waiting_result",
            expected_agent=expected_agent,
            instruction=f"wait for {agent_name} result",
        )
        _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)
        mode["status"] = f"{event_id.lower()}_waiting_for_agent_result"
        save_mode(ws, mode)
        return _g2_trace_result(mode, before_index, [])

    if signal == "agent-result":
        if event_id not in G2_SPAWN_POLICIES:
            raise StateError(f"active G2 event is {event_id}; cannot record agent result")
        policy = G2_SPAWN_POLICIES[event_id]
        expected_agent = policy["agent"]
        agent_name = agent.strip() or expected_agent
        if agent_name != expected_agent:
            raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")
        if not _has_agent_call(mode, event_id, expected_agent):
            raise StateError(f"{event_id} requires spawn_record before agent-result")
        _record_g2_agent_owned_result(mode, event_id, note)
        _trace_g2_agent_result_transition(mode, event_id, None, note)
        mode["status"] = f"{event_id.lower()}_waiting_for_inspector_spawn"
        save_mode(ws, mode)
        if design_path(mode).exists():
            _write_design(mode)
        return _g2_trace_result(mode, before_index, [])

    if signal == "inspector-spawn-record":
        if _inspector_state(mode).get("pending_event") != event_id:
            raise StateError(f"active G2 event is {event_id}; no inspector check is pending")
        agent_name = agent.strip() or INSPECTOR_AGENT
        if agent_name != INSPECTOR_AGENT:
            raise StateError(f"{event_id} requires agent {INSPECTOR_AGENT}, got {agent_name}")
        _record_g2_inspector_spawn(mode, event_id, agent_id)
        mode["status"] = f"{event_id.lower()}_waiting_for_inspector_result"
        save_mode(ws, mode)
        return _g2_trace_result(mode, before_index, [])

    if signal == "inspector-result":
        if _inspector_state(mode).get("pending_event") != event_id:
            raise StateError(f"active G2 event is {event_id}; no inspector check is pending")
        if not _has_agent_call(mode, event_id, INSPECTOR_AGENT):
            raise StateError(f"{event_id} requires inspector_spawn_record before inspector-result")
        _record_g2_inspector_result(mode, event_id, note)
        if event_id in G2_SPAWN_POLICIES:
            next_event = _complete_g2_after_inspector(mode, event_id)
            _trace_g2_next_after_inspector(mode, event_id, next_event)
            _set_orchestrator(
                mode,
                event_id,
                spawn_decision="spawned",
                spawn_status="completed",
                expected_agent=INSPECTOR_AGENT,
                instruction=f"Inspector completed; advance from {event_id}",
            )
            _inspector_state(mode).pop("pending_event", None)
            mode["status"] = f"{event_id.lower()}_done"
            save_mode(ws, mode)
            if design_path(mode).exists():
                _write_design(mode)
            return run_g2_hook_trace_until_user_gate(ws, before_index)
        if event_id == "G2.APPROVE_UI_DESIGN_PLAN":
            try:
                next_event = mark_active_event_terminal(mode, "G2.APPROVE_UI_DESIGN_PLAN", "done")
            except ValueError as exc:
                raise StateError(str(exc)) from exc
            _trace_g2_next_after_inspector(mode, event_id, next_event)
            _inspector_state(mode).pop("pending_event", None)
            mode["status"] = "g2_ui_design_plan_approved"
            save_mode(ws, mode)
            return run_g2_hook_trace_until_user_gate(ws, before_index)
        if event_id == "G2.DESIGN_PENCIL_STEPS":
            if _has_agent_call(mode, event_id, G2_PENCIL_DESIGN_AGENT):
                _mark_agent_call_completed(mode, event_id, G2_PENCIL_DESIGN_AGENT, "Pencil design completed")
            try:
                next_event = mark_active_event_terminal(mode, "G2.DESIGN_PENCIL_STEPS", "done")
            except ValueError as exc:
                raise StateError(str(exc)) from exc
            _complete_g2_design_item_tree(mode)
            _trace_g2_next_after_inspector(mode, event_id, next_event)
            _inspector_state(mode).pop("pending_event", None)
            mode["status"] = "g2_pencil_design_steps_done"
            save_mode(ws, mode)
            return run_g2_hook_trace_until_user_gate(ws, before_index)
        if event_id == "G2.USER_APPROVAL":
            approval_note = str(mode.pop("pending_g2_approval_note", "") or note).strip()
            save_mode(ws, mode)
            approve_g2(ws, note=approval_note)
            mode = load_mode(ws)
            assert mode is not None
            _inspector_state(mode).pop("pending_event", None)
            save_mode(ws, mode)
            return _g2_trace_result(mode, before_index, [])
        raise StateError(f"unsupported G2 inspector event: {event_id}")

    if signal == "approve-plan":
        if event_id != "G2.APPROVE_UI_DESIGN_PLAN":
            raise StateError(f"active G2 event is {event_id}; cannot record approve-plan")
        approve_g2_plan(ws, note=note)
        mode = load_mode(ws)
        assert mode is not None
        return _g2_trace_result(mode, before_index, [])

    if signal == "design-step":
        if event_id != "G2.DESIGN_PENCIL_STEPS":
            raise StateError(f"active G2 event is {event_id}; cannot record design-step")
        record_g2_design_step(ws, note=note, complete=complete)
        mode = load_mode(ws)
        assert mode is not None
        if complete:
            return _g2_trace_result(mode, before_index, [])
        return run_g2_hook_trace_until_user_gate(ws, before_index)

    if signal == "approve-g2":
        if event_id != "G2.USER_APPROVAL":
            raise StateError(f"active G2 event is {event_id}; cannot record approve-g2")
        if _event(mode, "G2.READINESS_CHECK").get("status") != "done":
            raise StateError("G2.READINESS_CHECK must be done before user approval")
        _ensure_g2_user_gate_waiting(mode, event_id)
        _trace_g2_hook(
            mode,
            "G2.USER_APPROVAL.record",
            note.strip() or "user approved G2",
            "G2.USER_APPROVAL",
            "record explicit G2 approval",
            {"approved_by": "user"},
        )
        mode["pending_g2_approval_note"] = note.strip()
        _require_g2_inspector(mode, event_id, "spawn inspector to check G2 approval before phase transition")
        save_mode(ws, mode)
        return _g2_trace_result(mode, before_index, [])

    raise StateError("signal must be one of: spawn-record, agent-result, inspector-spawn-record, inspector-result, approve-plan, design-step, approve-g2")


def _g2_trace_result(
    mode: dict[str, Any],
    before_index: int,
    advanced: list[dict[str, Any]],
) -> dict[str, Any]:
    current_event = None
    if not is_g2_complete(mode):
        current = active_event(mode, "G2") or blocked_event(mode, "G2")
        current_event = current.get("id") if current else None
    contract = _contract(mode)
    trace = _hook_trace(mode)
    return {
        "ok": True,
        "active_event": current_event,
        "complete": is_g2_complete(mode),
        "advanced": advanced,
        "trace": trace[before_index:],
        "trace_hooks": [item.get("hook") for item in trace[before_index:]],
        "ui_plan": contract.get("ui_plan") or [],
        "current_plan_item": _current_g2_plan_item(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "design": str(design_path(mode).resolve()),
    }


def _current_g2_plan_item(mode: dict[str, Any]) -> str | None:
    contract = _contract(mode)
    ui_plan = contract.get("ui_plan") or []
    steps = (contract.get("pencil_design") or {}).get("steps") or []
    if ui_plan and len(steps) < len(ui_plan):
        return str(ui_plan[len(steps)])
    return None


def _record_g2_agent_owned_result(mode: dict[str, Any], event_id: str, note: str = "") -> None:
    current = _event(mode, event_id)
    contract = _contract(mode)
    if event_id == "G2.DRAFT_UI_DESIGN_PLAN":
        if not (contract.get("ui") or {}).get("required"):
            raise StateError("G2.DRAFT_UI_DESIGN_PLAN is not applicable when UI is not required")
        contract["ui_plan"] = _ui_plan_from_agent_note(note) or _default_ui_plan(mode)
        current["answer_ref"] = "mode.json:g2_contract.ui_plan"
        return

    if event_id == "G2.REVIEW_SOURCE_PACK":
        manifest = _load_manifest(mode)
        files = manifest.get("files", [])
        if not files:
            raise StateError("source-manifest.json has no source files")
        contract["source_review"] = {
            "status": "reviewed",
            "reviewed_at": utc_now(),
            "note": note.strip(),
            "files": [
                {"path": item.get("path"), "kind": item.get("kind"), "sha256": item.get("sha256")}
                for item in files
            ],
        }
        return

    if event_id == "G2.DRAFT_DESIGN_CONTRACT":
        contract["status"] = "drafted"
        contract["drafted_at"] = utc_now()
        contract["design_decisions"] = [
            "Pencil .pen and frame ids are the UI authority for UI projects.",
            "02-design.md is generated from event_tree and g2_contract.",
            "Later stages must cite source refs and Pencil frame ids instead of relying on AI self-selection.",
        ]
        return

    if event_id == "G2.WRITE_DESIGN_ARTIFACT":
        contract["status"] = "written"
        path = _write_design(mode)
        current["answer_ref"] = str(path.resolve())
        return

    raise StateError(f"unsupported G2 agent-owned event: {event_id}")


def _complete_g2_after_inspector(mode: dict[str, Any], event_id: str) -> dict[str, Any] | None:
    contract = _contract(mode)
    current = _event(mode, event_id)
    if event_id == "G2.REVIEW_SOURCE_PACK" and not (contract.get("ui") or {}).get("required"):
        current["status"] = "done"
        for skip_event in PENCIL_VALIDATION_EVENTS:
            set_event_status(mode, skip_event, "not_applicable")
        next_event = event_by_id(mode, "G2.DRAFT_DESIGN_CONTRACT")
        next_event["status"] = "active"
        return next_event
    if event_id == "G2.DRAFT_DESIGN_CONTRACT" and not (contract.get("ui") or {}).get("required"):
        current["status"] = "done"
        next_event = event_by_id(mode, "G2.WRITE_DESIGN_ARTIFACT")
        next_event["status"] = "active"
        return next_event
    return _complete_current(mode, event_id)


def _trace_g2_next_after_inspector(mode: dict[str, Any], event_id: str, next_event: dict[str, Any] | None) -> None:
    if next_event is None:
        return
    next_id = str(next_event.get("id") or "")
    if next_id == "G2.DESIGN_PENCIL_STEPS":
        _activate_g2_design_item_tree(mode)
    _trace_g2_hook(
        mode,
        f"{event_id}.next",
        f"{event_id}=done",
        event_id,
        f"advance to {next_id}",
    )
    if next_id in G2_USER_GATE_EVENTS and not _has_hook(mode, f"{next_id}.enter"):
        _trace_g2_hook_once(
            mode,
            f"{next_id}.enter",
            f"{next_id}=active",
            next_id,
            f"enter user interaction gate {next_id}",
        )


def advance_g2(ws: Workspace, note: str = "", *, trace: bool = True) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g2":
        raise StateError("G2 can only advance while stage=g2")
    _ensure_g2_design_item_group(mode)
    current = _active_g2_event(mode)
    event_id = str(current.get("id"))
    contract = _contract(mode)

    if event_id == "G2.START":
        if not is_g1_complete(mode):
            raise StateError("G2.START requires G1.COMPLETE")
        current["completed_at"] = utc_now()
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.READ_G1_DEFINITION":
        contract_path = _path_in_run(mode, "project-definition.json")
        markdown_path = _path_in_run(mode, "01-project-definition.md")
        if not contract_path.exists():
            _block_current(mode, current, "project-definition.json is missing")
            save_mode(ws, mode)
            raise StateError("project-definition.json is missing")
        if not markdown_path.exists():
            _block_current(mode, current, "01-project-definition.md is missing")
            save_mode(ws, mode)
            raise StateError("01-project-definition.md is missing")
        contract["project_definition_contract"] = {
            "path": str(contract_path.resolve()),
            "sha256": file_sha256(contract_path),
            "schema": read_json(contract_path, {}).get("schema"),
            "read_at": utc_now(),
        }
        contract["project_definition"] = {
            "path": str(markdown_path.resolve()),
            "sha256": file_sha256(markdown_path),
            "read_at": utc_now(),
        }
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.CHECK_UI_REQUIREMENT":
        required = _ui_required(mode)
        contract["ui"] = {
            "required": required,
            "authority": "pencil" if required else "NO_UI",
            "source": "G1.Q4",
            "source_answer": _g1_answer(mode, "G1.Q4"),
        }
        current["status"] = "done"
        if required:
            next_event = event_by_id(mode, "G2.DRAFT_UI_DESIGN_PLAN")
            next_event["status"] = "active"
        else:
            for skip_event in PENCIL_SKIP_EVENTS:
                set_event_status(mode, skip_event, "not_applicable")
            set_event_status(mode, G2_DESIGN_ITEM_GROUP_ID, "not_applicable")
            next_event = event_by_id(mode, "G2.REFRESH_SOURCE_PACK")
            next_event["status"] = "active"

    elif event_id == "G2.DRAFT_UI_DESIGN_PLAN":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.REFRESH_SOURCE_PACK")
            next_event["status"] = "active"
        else:
            contract["ui_plan"] = _default_ui_plan(mode)
            current["answer_ref"] = "mode.json:g2_contract.ui_plan"
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.APPROVE_UI_DESIGN_PLAN":
        raise StateError("use g2-approve-plan to record explicit user approval for the UI design plan")

    elif event_id == "G2.CREATE_PENCIL_PROJECT":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.REFRESH_SOURCE_PACK")
            next_event["status"] = "active"
        else:
            path = _ensure_pencil_project(ws, mode)
            ui = contract.setdefault("ui", {"required": True, "authority": "pencil"})
            ui["pencil_project"] = str(path.resolve())
            current["answer_ref"] = str(path.resolve())
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.OPEN_PENCIL":
        ui = contract.setdefault("ui", {"required": True, "authority": "pencil"})
        pencil_project = Path(str(ui.get("pencil_project") or ""))
        if not pencil_project.exists():
            _block_current(mode, current, "Pencil project file is missing")
            save_mode(ws, mode)
            raise StateError("Pencil project file is missing")
        ui["pencil_opened_at"] = utc_now()
        current["answer_ref"] = str(pencil_project.resolve())
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.DESIGN_PENCIL_STEPS":
        raise StateError("use g2-design-step to record user-steered Pencil design progress; pass --complete after the user design-done signal")

    elif event_id == "G2.REFRESH_SOURCE_PACK":
        from .stages import rebuild_source_and_maps

        result = rebuild_source_and_maps(ws, Path(mode["run_dir"]))
        mode["source_pack"] = {
            "file_count": len(result["manifest"].get("files", [])),
            "pencil_frame_count": len(result["inventory"].get("frames", [])),
            "feature_ui_map_status": result["mapping"].get("status"),
        }
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.REVIEW_SOURCE_PACK":
        manifest = _load_manifest(mode)
        files = manifest.get("files", [])
        if not files:
            _block_current(mode, current, "source-manifest.json has no source files")
            save_mode(ws, mode)
            raise StateError("source-manifest.json has no source files")
        contract["source_review"] = {
            "status": "reviewed",
            "reviewed_at": utc_now(),
            "note": note.strip(),
            "files": [
                {"path": item.get("path"), "kind": item.get("kind"), "sha256": item.get("sha256")}
                for item in files
            ],
        }
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "done"
            for skip_event in PENCIL_VALIDATION_EVENTS:
                set_event_status(mode, skip_event, "not_applicable")
            next_event = event_by_id(mode, "G2.DRAFT_DESIGN_CONTRACT")
            next_event["status"] = "active"
        else:
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.EXTRACT_PENCIL_FRAMES":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.DRAFT_DESIGN_CONTRACT")
            next_event["status"] = "active"
            mode["status"] = f"{event_id.lower()}_not_applicable"
            if trace:
                _trace_g2_transition(mode, event_id, next_event, note)
            save_mode(ws, mode)
            return {
                "ok": True,
                "event": event_id,
                "status": "not_applicable",
                "next_event": next_event.get("id") if next_event else None,
                "design": str(design_path(mode).resolve()),
            }
        pencil_files = _pencil_files_from_manifest(mode)
        if not pencil_files:
            _block_current(mode, current, "UI project requires a Pencil .pen source file")
            save_mode(ws, mode)
            raise StateError("UI project requires a Pencil .pen source file")
        ui = contract.setdefault("ui", {"required": True, "authority": "pencil"})
        ui["pencil_files"] = [
            {"path": item.get("path"), "absolute_path": item.get("absolute_path"), "sha256": item.get("sha256")}
            for item in pencil_files
        ]
        inventory = _load_inventory(mode)
        frames = inventory.get("frames", [])
        if int(inventory.get("frame_count", 0) or 0) <= 0:
            _block_current(mode, current, "Pencil files exist but no frames were extracted")
            save_mode(ws, mode)
            raise StateError("Pencil files exist but no frames were extracted")
        contract.setdefault("ui", {"required": True, "authority": "pencil"})["frames"] = frames
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.MAP_FEATURE_TO_PENCIL_FRAME":
        mapping = _load_mapping(mode)
        ui = contract.setdefault("ui", {"required": True, "authority": "pencil"})
        ui["feature_ui_map_status"] = mapping.get("status")
        ui["references"] = mapping.get("references", {})
        ui["missing_frame_references"] = mapping.get("missing_frame_references", {})
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.CHECK_FEATURE_UI_MAP":
        mapping = _load_mapping(mode)
        if mapping.get("status") != "ok":
            _block_current(mode, current, f"feature-ui-map status must be ok for UI projects, got {mapping.get('status')!r}")
            save_mode(ws, mode)
            raise StateError(f"feature-ui-map status must be ok for UI projects, got {mapping.get('status')!r}")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.MAP_PENCIL_TO_CODE_TARGETS":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.EXTRACT_LAYOUT_SPEC")
            next_event["status"] = "active"
        else:
            mapping = g3_design._default_ui_code_map(mode, note)
            if mapping.get("status") != "ok":
                _block_current(mode, current, f"ui-code-map status must be ok, got {mapping.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["ui_code_map"] = mapping
            contract["deliverables"]["ui_code_map"] = str(_path_in_run(mode, "ui-code-map.json").resolve())
            g3_design._write_ui_code_map(mode, mapping)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.EXTRACT_LAYOUT_SPEC":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.EXTRACT_DESIGN_TOKENS")
            next_event["status"] = "active"
        else:
            spec = g3_design._default_layout_spec(mode)
            if spec.get("status") != "ok":
                _block_current(mode, current, f"ui-layout-spec status must be ok, got {spec.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["layout_spec"] = spec
            contract["deliverables"]["layout_spec"] = str(_path_in_run(mode, "ui-layout-spec.json").resolve())
            g3_design._write_layout_spec(mode, spec)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.EXTRACT_DESIGN_TOKENS":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.MAP_INTERACTION_STATES")
            next_event["status"] = "active"
        else:
            tokens = g3_design._default_design_tokens(mode)
            contract["design_tokens"] = tokens
            contract["deliverables"]["design_tokens"] = str(_path_in_run(mode, "design-tokens.json").resolve())
            g3_design._write_design_tokens(mode, tokens)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.MAP_INTERACTION_STATES":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.WRITE_VISUAL_ACCEPTANCE")
            next_event["status"] = "active"
        else:
            state_map = g3_design._default_interaction_state_map(mode)
            if state_map.get("status") != "ok":
                _block_current(mode, current, f"interaction-state-map status must be ok, got {state_map.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["interaction_state_map"] = state_map
            contract["deliverables"]["interaction_state_map"] = str(_path_in_run(mode, "interaction-state-map.json").resolve())
            g3_design._write_interaction_state_map(mode, state_map)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.WRITE_VISUAL_ACCEPTANCE":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.CHECK_UI_IMPLEMENTATION_CONTRACT")
            next_event["status"] = "active"
        else:
            acceptance = g3_design._default_visual_acceptance(mode)
            if acceptance.get("status") != "ok":
                _block_current(mode, current, f"visual-acceptance status must be ok, got {acceptance.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["visual_acceptance"] = acceptance
            contract["deliverables"]["visual_acceptance"] = str(_path_in_run(mode, "visual-acceptance.json").resolve())
            try:
                g3_design._ensure_pencil_reference_screenshots(mode, acceptance)
            except StateError as exc:
                _block_current(mode, current, str(exc))
                save_mode(ws, mode)
                raise
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.CHECK_UI_IMPLEMENTATION_CONTRACT":
        try:
            g3_design._assert_ui_implementation_contract_ready(mode)
        except StateError as exc:
            _block_current(mode, current, str(exc))
            save_mode(ws, mode)
            raise
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.WRITE_PENCIL_CONTRACT_MAP":
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.CHECK_PENCIL_CONTRACT_MAP")
            next_event["status"] = "active"
        else:
            contract_map = g3_design._default_pencil_contract_map(mode)
            if contract_map.get("status") != "ok":
                _block_current(mode, current, f"pencil-contract-map status must be ok, got {contract_map.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["pencil_contract_map"] = contract_map
            contract["deliverables"]["pencil_contract_map"] = str(_path_in_run(mode, "pencil-contract-map.json").resolve())
            g3_design._write_pencil_contract_map(mode, contract_map)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.CHECK_PENCIL_CONTRACT_MAP":
        try:
            g3_design._assert_pencil_contract_map_ready(mode)
        except StateError as exc:
            _block_current(mode, current, str(exc))
            save_mode(ws, mode)
            raise
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.DRAFT_DESIGN_CONTRACT":
        contract["status"] = "drafted"
        contract["drafted_at"] = utc_now()
        contract["design_decisions"] = [
            "Pencil .pen and frame ids are the UI authority for UI projects.",
            "02-design.md is generated from event_tree and g2_contract.",
            "Later stages must cite source refs and Pencil frame ids instead of relying on AI self-selection.",
        ]
        if not (contract.get("ui") or {}).get("required"):
            current["status"] = "done"
            next_event = event_by_id(mode, "G2.WRITE_DESIGN_ARTIFACT")
            next_event["status"] = "active"
        else:
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.DELIVER_PENCIL_DESIGN":
        ui = contract.get("ui") or {}
        if not ui.get("required"):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G2.WRITE_DESIGN_ARTIFACT")
            next_event["status"] = "active"
        else:
            frames = ui.get("frames") or []
            if not frames:
                _block_current(mode, current, "Pencil frames must be extracted before delivery")
                save_mode(ws, mode)
                raise StateError("Pencil frames must be extracted before delivery")
            pencil_design = contract.setdefault("pencil_design", {"steps": [], "deliverables": []})
            pencil_design["deliverables"] = [
                "Pencil .pen source",
                "frame-inventory.json",
                "feature-ui-map.json",
                "ui-code-map.json",
                "ui-layout-spec.json",
                "design-tokens.json",
                "interaction-state-map.json",
                "visual-acceptance.json",
                "pencil-contract-map.json",
                "evidence/g2/reference/*.png",
                "UI frame list",
                "G1 feature to UI frame mapping",
            ]
            current["answer_ref"] = "mode.json:g2_contract.pencil_design.deliverables"
            next_event = _complete_current(mode, event_id)

    elif event_id == "G2.WRITE_DESIGN_ARTIFACT":
        contract["status"] = "written"
        path = _write_design(mode)
        current["answer_ref"] = str(path.resolve())
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.READINESS_CHECK":
        _assert_g2_ready(mode)
        contract["status"] = "ready_for_user_approval"
        current["completed_at"] = utc_now()
        next_event = _complete_current(mode, event_id)

    elif event_id == "G2.USER_APPROVAL":
        raise StateError("use g2-approve to record explicit user approval")

    else:
        raise StateError(f"unsupported G2 event: {event_id}")

    mode["status"] = f"{event_id.lower()}_done"
    if trace:
        _trace_g2_transition(mode, event_id, next_event, note)
    save_mode(ws, mode)
    if design_path(mode).exists():
        _write_design(mode)
    return {
        "ok": True,
        "event": event_id,
        "status": "done",
        "next_event": next_event.get("id") if next_event else None,
        "design": str(design_path(mode).resolve()),
    }


def _assert_g2_ready(mode: dict[str, Any]) -> None:
    contract = _contract(mode)
    ui = contract.get("ui") or {}
    required_done = [
        "G2.START",
        "G2.READ_G1_DEFINITION",
        "G2.CHECK_UI_REQUIREMENT",
        "G2.REFRESH_SOURCE_PACK",
        "G2.REVIEW_SOURCE_PACK",
        "G2.DRAFT_DESIGN_CONTRACT",
        "G2.WRITE_DESIGN_ARTIFACT",
    ]
    for event_id in required_done:
        if _event(mode, event_id).get("status") != "done":
            raise StateError(f"{event_id} must be done before G2.READINESS_CHECK")
    if ui.get("required"):
        for event_id in PENCIL_SKIP_EVENTS:
            if _event(mode, event_id).get("status") != "done":
                raise StateError(f"{event_id} must be done for UI projects")
        if ui.get("feature_ui_map_status") != "ok":
            raise StateError("feature-ui-map status must be ok for UI projects")
        g3_design._assert_ui_implementation_contract_ready(mode)
        g3_design._assert_pencil_contract_map_ready(mode)
    else:
        for event_id in PENCIL_SKIP_EVENTS:
            if _event(mode, event_id).get("status") != "not_applicable":
                raise StateError(f"{event_id} must be not_applicable for non-UI projects")
    if not contract.get("project_definition_contract"):
        raise StateError("g2_contract.project_definition_contract is missing")
    if not contract.get("source_review"):
        raise StateError("g2_contract.source_review is missing")


def approve_g2_plan(ws: Workspace, approved_by: str = "user", note: str = "") -> dict[str, Any]:
    if approved_by != "user":
        raise StateError("G2 UI design plan approval must be approved_by='user'")
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g2":
        raise StateError("G2 UI design plan approval can only be recorded while stage=g2")
    current = _active_g2_event(mode)
    if current.get("id") != "G2.APPROVE_UI_DESIGN_PLAN":
        raise StateError(f"active G2 event is {current.get('id')}; cannot approve UI design plan")
    if not _contract(mode).get("ui_plan"):
        raise StateError("G2 UI design plan is missing")
    now = utc_now()
    current["answer_ref"] = "mode.json:g2_contract.ui_plan"
    current["approved_by"] = approved_by
    current["approved_at"] = now
    current["approval_note"] = note.strip()
    _materialize_g2_design_item_tree(mode)
    if not _has_hook(mode, "G2.APPROVE_UI_DESIGN_PLAN.enter"):
        _trace_g2_hook(
            mode,
            "G2.APPROVE_UI_DESIGN_PLAN.enter",
            "G2.APPROVE_UI_DESIGN_PLAN=active",
            "G2.APPROVE_UI_DESIGN_PLAN",
            "show UI design plan and wait for user approval",
        )
    _trace_g2_hook(
        mode,
        "G2.APPROVE_UI_DESIGN_PLAN.record",
        note.strip() or "user approved UI design plan",
        "G2.APPROVE_UI_DESIGN_PLAN",
        "record explicit user approval",
        {"approved_by": approved_by},
    )
    _require_g2_inspector(
        mode,
        "G2.APPROVE_UI_DESIGN_PLAN",
        "spawn inspector to check G2 UI design-plan approval before next",
    )
    mode["status"] = "g2_ui_design_plan_waiting_for_inspector_spawn"
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": "G2.APPROVE_UI_DESIGN_PLAN",
        "status": "waiting_for_inspector",
        "next_event": "G2.APPROVE_UI_DESIGN_PLAN",
    }


def record_g2_design_step(ws: Workspace, note: str, complete: bool = False) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g2":
        raise StateError("G2 Pencil design progress can only be recorded while stage=g2")
    current = _active_g2_event(mode)
    if current.get("id") != "G2.DESIGN_PENCIL_STEPS":
        raise StateError(f"active G2 event is {current.get('id')}; cannot record Pencil design progress")
    if not _has_agent_call(mode, "G2.DESIGN_PENCIL_STEPS", G2_PENCIL_DESIGN_AGENT):
        raise StateError("G2.DESIGN_PENCIL_STEPS requires designer spawn_record before design-step")
    _activate_g2_design_item_tree(mode)
    text = note.strip()
    if not text:
        raise StateError("design step note is required")
    contract = _contract(mode)
    ui_plan = contract.get("ui_plan") or []
    pencil_design = contract.setdefault("pencil_design", {"steps": [], "deliverables": []})
    steps = pencil_design.setdefault("steps", [])
    if ui_plan and len(steps) >= len(ui_plan):
        raise StateError("all G2 UI design plan items have already been recorded")
    step_number = len(steps) + 1
    planned_item = ui_plan[len(steps)] if ui_plan else ""
    steps.append({"plan_item": planned_item, "note": text, "recorded_at": utc_now()})
    _mark_g2_design_item_recorded(mode, step_number, text)
    step_hook = f"G2.DESIGN_PENCIL_STEPS.item{step_number}"
    _trace_g2_hook_once(
        mode,
        f"{step_hook}.enter",
        f"plan_item={planned_item}",
        "G2.DESIGN_PENCIL_STEPS",
        f"start Pencil design item {step_number}",
        {"plan_item": planned_item, "step_number": step_number},
    )
    _trace_g2_hook_once(
        mode,
        f"{step_hook}.hold",
        "waiting for user-steered Pencil design",
        "G2.DESIGN_PENCIL_STEPS",
        f"hold at Pencil design item {step_number}",
        {"plan_item": planned_item, "step_number": step_number},
    )
    _trace_g2_hook(
        mode,
        f"{step_hook}.record",
        text,
        "G2.DESIGN_PENCIL_STEPS",
        f"record Pencil design item {step_number}",
        {"plan_item": planned_item, "step_number": step_number},
    )
    _set_orchestrator(
        mode,
        "G2.DESIGN_PENCIL_STEPS",
        spawn_decision="none",
        spawn_status="not_required",
        expected_agent=None,
        instruction="record user-steered Pencil design progress",
    )
    _set_inspector(mode, "G2.DESIGN_PENCIL_STEPS", status="not_required", checkpoint_required=False)
    current["answer_ref"] = "mode.json:g2_contract.pencil_design.steps"
    next_plan_item = ui_plan[len(steps)] if ui_plan and len(steps) < len(ui_plan) else None
    if complete:
        if ui_plan and len(steps) < len(ui_plan):
            raise StateError(
                f"G2.DESIGN_PENCIL_STEPS cannot complete before all UI design plan items are recorded; "
                f"recorded={len(steps)} required={len(ui_plan)} next_item={ui_plan[len(steps)]}"
            )
        _trace_g2_hook(
            mode,
            "G2.DESIGN_PENCIL_STEPS.record",
            "user design-done signal",
            "G2.DESIGN_PENCIL_STEPS",
            "record Pencil design completion",
        )
        _require_g2_inspector(
            mode,
            "G2.DESIGN_PENCIL_STEPS",
            "spawn inspector to check Pencil design steps before next",
        )
        next_event = current
        mode["status"] = "g2_pencil_design_steps_waiting_for_inspector_spawn"
    else:
        next_event = current
        mode["status"] = "g2_pencil_design_steps_active"
        _activate_g2_design_item_tree(mode)
        if next_plan_item is not None:
            _trace_g2_hook(
                mode,
                f"{step_hook}.next",
                f"item{step_number}=done",
                "G2.DESIGN_PENCIL_STEPS",
                f"advance to Pencil design item {step_number + 1}",
                {"next_plan_item": next_plan_item, "step_number": step_number},
            )
            _trace_g2_hook_once(
                mode,
                f"G2.DESIGN_PENCIL_STEPS.item{step_number + 1}.enter",
                f"plan_item={next_plan_item}",
                "G2.DESIGN_PENCIL_STEPS",
                f"show Pencil design item {step_number + 1}",
                {"plan_item": next_plan_item, "step_number": step_number + 1},
            )
            _trace_g2_hook_once(
                mode,
                f"G2.DESIGN_PENCIL_STEPS.item{step_number + 1}.hold",
                "waiting for user-steered Pencil design",
                "G2.DESIGN_PENCIL_STEPS",
                f"hold at Pencil design item {step_number + 1}",
                {"plan_item": next_plan_item, "step_number": step_number + 1},
            )
        else:
            _trace_g2_hook(
                mode,
                "G2.DESIGN_PENCIL_STEPS.hold",
                "all plan items recorded without design-done signal",
                "G2.DESIGN_PENCIL_STEPS",
                "wait for explicit Pencil design-done signal",
            )
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": "G2.DESIGN_PENCIL_STEPS",
        "status": "done" if complete else "active",
        "recorded_steps": len(steps),
        "required_steps": len(ui_plan),
        "current_plan_item": planned_item,
        "next_plan_item": next_plan_item,
        "next_event": next_event.get("id") if next_event else None,
    }


def approve_g2(ws: Workspace, approved_by: str = "user", note: str = "") -> dict[str, Any]:
    if approved_by != "user":
        raise StateError("G2 approval must be approved_by='user'")
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    if mode.get("stage") != "g2":
        raise StateError("G2 approval can only be recorded while stage=g2")
    if _event(mode, "G2.READINESS_CHECK").get("status") != "done":
        raise StateError("G2.READINESS_CHECK must be done before user approval")
    current = _active_g2_event(mode)
    if current.get("id") != "G2.USER_APPROVAL":
        raise StateError(f"active G2 event is {current.get('id')}; cannot approve G2")
    now = utc_now()
    current["answer_ref"] = "02-design.md#approval"
    current["approved_at"] = now
    if not _has_hook(mode, "G2.USER_APPROVAL.enter"):
        _trace_g2_hook(
            mode,
            "G2.USER_APPROVAL.enter",
            "G2.USER_APPROVAL=active",
            "G2.USER_APPROVAL",
            "show G2 design artifact and wait for user approval",
        )
    if not _has_hook(mode, "G2.USER_APPROVAL.record"):
        _trace_g2_hook(
            mode,
            "G2.USER_APPROVAL.record",
            note.strip() or "user approved G2",
            "G2.USER_APPROVAL",
            "record explicit G2 approval",
            {"approved_by": approved_by},
        )
    _set_orchestrator(
        mode,
        "G2.USER_APPROVAL",
        spawn_decision="none",
        spawn_status="not_required",
        expected_agent=None,
        instruction="G2 approved; advance to G3",
    )
    try:
        mark_active_event_terminal(mode, "G2.USER_APPROVAL", "done")
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    complete = _event(mode, "G2.COMPLETE")
    complete["status"] = "done"
    complete["completed_at"] = now
    mode["g2_approval"] = {
        "status": "approved",
        "approved_by": approved_by,
        "approved_at": now,
        "note": note.strip(),
    }
    _contract(mode)["status"] = "approved"
    try:
        transition_to_phase(mode, "G3")
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    _trace_g2_hook(
        mode,
        "G2.USER_APPROVAL.next",
        "G2.COMPLETE=done",
        "G2.USER_APPROVAL",
        "advance to G3",
    )
    mode["status"] = "g3_ready_for_plan"
    save_mode(ws, mode)
    path = _write_design(mode)
    return {
        "ok": True,
        "event": "G2.COMPLETE",
        "status": "done",
        "next_global_event": "G3",
        "next_event": active_event(mode, "G3").get("id") if active_event(mode, "G3") else None,
        "design": str(path.resolve()),
    }
