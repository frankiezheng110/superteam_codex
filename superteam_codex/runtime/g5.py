from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from .agent_registry import agent_spawn_contract, require_superteam_agent
from .event_tree import (
    G5_EVENT_IDS,
    active_event,
    blocked_event,
    child_events,
    event_by_id,
    g5_event_nodes,
    mark_active_event_terminal,
    transition_to_phase,
)
from .state import StateError, load_mode, save_mode, validate_mode
from .workspace import Workspace, file_sha256, read_json, utc_now


REVIEWER_AGENT = require_superteam_agent("reviewer", context="G5.SPAWN_REVIEWER")
DESIGNER_AGENT = require_superteam_agent("designer", context="G5.UI_QUALITY_REVIEW")

REVIEW_INPUT_FILES = [
    "01-project-definition.md",
    "02-design.md",
    "04-plan.md",
    "05-execution.md",
    "implementation-plan.json",
    "ui-code-map.json",
    "ui-layout-spec.json",
    "design-tokens.json",
    "interaction-state-map.json",
    "visual-acceptance.json",
]


def _event_tree_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    tree = mode.setdefault("event_tree", [])
    if not isinstance(tree, list):
        raise StateError("mode.event_tree is missing or invalid")
    return tree


def _ensure_g5_event_tree(mode: dict[str, Any]) -> bool:
    existing = {item.get("id") for item in _event_tree_items(mode) if isinstance(item, dict)}
    if all(event_id in existing for event_id in G5_EVENT_IDS) and "G5.REVIEW_DELIVERY" not in existing:
        return False
    tree = [
        item
        for item in _event_tree_items(mode)
        if not (isinstance(item, dict) and item.get("phase") == "G5" and item.get("id") != "G5")
    ]
    mode["event_tree"] = tree + g5_event_nodes()
    if event_by_id(mode, "G5").get("status") == "active":
        event_by_id(mode, "G5.START")["status"] = "active"
    return True


def _event(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    try:
        return event_by_id(mode, event_id)
    except KeyError as exc:
        raise StateError(str(exc)) from exc


def _active_g5_event(mode: dict[str, Any]) -> dict[str, Any]:
    current = active_event(mode, "G5")
    if current is None:
        blocked = blocked_event(mode, "G5")
        if blocked is not None:
            raise StateError(f"G5 is blocked at {blocked.get('id')}: {blocked.get('blocked_reason', '')}")
        raise StateError("G5 must have exactly one active event before completion")
    return current


def _path_in_run(mode: dict[str, Any], name: str) -> Path:
    return Path(mode["run_dir"]) / name


def review_path(mode: dict[str, Any]) -> Path:
    return _path_in_run(mode, "06-review.md")


def _contract(mode: dict[str, Any]) -> dict[str, Any]:
    contract = mode.setdefault("g5_contract", {})
    contract.setdefault("status", "pending")
    contract.setdefault("review_inputs", [])
    contract.setdefault("reviewer", None)
    contract.setdefault("review_evidence", None)
    contract.setdefault("ui_quality", {"required": False, "designer": None})
    contract.setdefault("verdict", None)
    contract.setdefault("findings", [])
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


def _trace_g5_hook(
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


def _trace_g5_hook_once(
    mode: dict[str, Any],
    hook: str,
    trigger: str,
    event_id: str,
    instruction: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if not _has_hook(mode, hook):
        _trace_g5_hook(mode, hook, trigger, event_id, instruction, extra)


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


def _set_inspector_not_required(mode: dict[str, Any], event_id: str) -> None:
    inspector = _inspector_state(mode)
    inspector["active_event"] = event_id
    inspector["status"] = "not_required"
    inspector["checkpoint_required"] = False
    inspector["gate_check_report"] = {"status": "not_required", "checked_event": event_id, "findings": []}
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
    _trace_g5_hook(mode, f"{event_id}.record", "runtime recorded event result", event_id, f"record {event_id}")
    if next_event is not None:
        next_id = str(next_event.get("id") or "")
        _trace_g5_hook(mode, f"{event_id}.next", f"{event_id}={status}", event_id, f"advance to {next_id}")
        _trace_g5_hook_once(mode, f"{next_id}.enter", f"{next_id}=active", next_id, "enter active G5 event")
        _set_orchestrator(
            mode,
            next_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction=f"complete {next_id} or stop at its hook gate",
        )
        _set_inspector_not_required(mode, next_id)
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


def _collect_review_inputs(mode: dict[str, Any]) -> list[dict[str, Any]]:
    return [_artifact_record(mode, name) for name in REVIEW_INPUT_FILES]


def _load_json_artifact(mode: dict[str, Any], name: str) -> dict[str, Any]:
    data = read_json(_path_in_run(mode, name), {})
    return data if isinstance(data, dict) else {}


def _implementation_plan(mode: dict[str, Any]) -> dict[str, Any]:
    plan = _load_json_artifact(mode, "implementation-plan.json")
    if not plan:
        plan = (_contract(mode).get("review_inputs") or {})
    return plan if isinstance(plan, dict) else {}


def _ui_work_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    plan = _load_json_artifact(mode, "implementation-plan.json")
    items = plan.get("work_items") if isinstance(plan.get("work_items"), list) else []
    return [item for item in items if isinstance(item, dict) and str(item.get("kind") or "").lower() == "ui"]


def _is_ui_project(mode: dict[str, Any]) -> bool:
    ui_map = _load_json_artifact(mode, "ui-code-map.json")
    mappings = ui_map.get("mappings") if isinstance(ui_map.get("mappings"), list) else []
    if ui_map.get("status") == "ok" and mappings:
        return True
    return bool(_ui_work_items(mode))


def _ui_guidance_payload(mode: dict[str, Any]) -> dict[str, Any]:
    ui_map = _load_json_artifact(mode, "ui-code-map.json")
    layout = _load_json_artifact(mode, "ui-layout-spec.json")
    tokens = _load_json_artifact(mode, "design-tokens.json")
    interaction = _load_json_artifact(mode, "interaction-state-map.json")
    visual = _load_json_artifact(mode, "visual-acceptance.json")
    g4_tdd = ((mode.get("g4_contract") or {}).get("tdd") or {}) if isinstance(mode.get("g4_contract"), dict) else {}
    items = g4_tdd.get("items") if isinstance(g4_tdd.get("items"), dict) else {}
    g4_guidance = {
        item_id: item.get("ui_guidance")
        for item_id, item in items.items()
        if isinstance(item, dict) and isinstance(item.get("ui_guidance"), dict)
    }
    return {
        "ui_code_map": ui_map,
        "layout_spec_status": layout.get("status"),
        "design_tokens_status": tokens.get("status"),
        "interaction_state_status": interaction.get("status"),
        "visual_acceptance": visual,
        "g4_ui_guidance": g4_guidance,
    }


def _trace_review_guidance(mode: dict[str, Any], event_id: str) -> None:
    inputs = _collect_review_inputs(mode)
    _contract(mode)["review_inputs"] = inputs
    missing = [item["name"] for item in inputs if not item.get("exists") and not item["name"].startswith("ui-")]
    repair_context = _contract(mode).get("repair_context")
    instruction = (
        "guide reviewer before review: read G1/G2/G3/G4 artifacts, compare execution to approved plan, "
        "check TDD red/green evidence, delivery scope, tests, and artifact completeness"
    )
    if isinstance(repair_context, dict) and repair_context:
        instruction = (
            f"{instruction}; this is repair iteration {repair_context.get('iteration')} after "
            f"G6 {repair_context.get('verdict')}, so check that the failed verification items were corrected"
        )
    _trace_g5_hook_once(
        mode,
        "G5.REVIEW_GUIDANCE.inputs",
        "before reviewer spawn",
        event_id,
        instruction,
        {"review_inputs": inputs, "missing_required_inputs": missing, "repair_context": repair_context},
    )
    if _is_ui_project(mode):
        payload = _ui_guidance_payload(mode)
        _trace_g5_hook_once(
            mode,
            "G5.UI_REVIEW_GUIDANCE",
            "ui_project=true",
            event_id,
            (
                "guide reviewer before UI review: compare implementation screenshots and layout against "
                "Pencil-derived ui-code-map, ui-layout-spec, design-tokens, interaction-state-map, "
                "visual-acceptance, and G4 pre-implementation UI guidance"
            ),
            {"ui_review_guidance": payload},
        )
        for item in _ui_work_items(mode):
            frame_ids = [str(value) for value in item.get("frame_ids") or [] if str(value).strip()]
            frame_key = "_".join(frame_ids) if frame_ids else str(item.get("id") or "ui")
            _trace_g5_hook_once(
                mode,
                f"G5.UI_REVIEW_GUIDANCE.{frame_key}",
                f"ui_work_item={item.get('id')}",
                event_id,
                (
                    "guide UI quality review before judgment: verify frame fidelity, layout, tokens, states, "
                    "visual acceptance, and planned code targets"
                ),
                {"ui_work_item": item},
            )


def _ensure_g5_reviewer_required(mode: dict[str, Any]) -> None:
    event_id = "G5.SPAWN_REVIEWER"
    _trace_g5_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter reviewer spawn gate")
    _trace_review_guidance(mode, event_id)
    _trace_g5_hook_once(
        mode,
        f"{event_id}.spawn_required",
        f"expected_agent={REVIEWER_AGENT}",
        event_id,
        "spawn reviewer for deliverable-quality gate; OR must not impersonate reviewer",
        {"expected_agent": REVIEWER_AGENT, **agent_spawn_contract(REVIEWER_AGENT)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=REVIEWER_AGENT,
        instruction="spawn reviewer; provide G5 review guidance and original SuperTeam reviewer rules before review starts",
    )
    _set_inspector_not_required(mode, event_id)


def _ensure_designer_required(mode: dict[str, Any]) -> None:
    event_id = "G5.UI_QUALITY_REVIEW"
    _trace_g5_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter UI quality review gate")
    _trace_g5_hook_once(
        mode,
        f"{event_id}.designer_required",
        f"expected_agent={DESIGNER_AGENT}",
        event_id,
        "spawn designer to participate in UI quality gate before verification",
        {"expected_agent": DESIGNER_AGENT, **agent_spawn_contract(DESIGNER_AGENT), "ui_review_guidance": _ui_guidance_payload(mode)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=DESIGNER_AGENT,
        instruction="spawn designer for UI fidelity review against Pencil and G3/G4 UI contracts",
    )
    _set_inspector_not_required(mode, event_id)
    _contract(mode)["ui_quality"] = {"required": True, "designer": _contract(mode).get("ui_quality", {}).get("designer")}


def _review_verdict(text: str) -> str | None:
    match = re.search(r"(?im)^\s*(?:verdict|recommendation|status)\s*:\s*(CLEAR_WITH_CONCERNS|CLEAR|BLOCK)\b", text)
    if match:
        return match.group(1)
    match = re.search(r"(?im)\b(CLEAR_WITH_CONCERNS|CLEAR|BLOCK)\b", text)
    return match.group(1) if match else None


def _has_section(text: str, title_pattern: str) -> bool:
    return bool(re.search(rf"(?im)^#+\s*{title_pattern}\b", text) or re.search(title_pattern, text, re.IGNORECASE))


def _extract_section(text: str, title_pattern: str) -> str:
    pattern = re.compile(rf"(?ims)^#+\s*{title_pattern}\b[^\n]*\n(?P<body>.*?)(?=^#+\s|\Z)")
    match = pattern.search(text)
    return match.group("body") if match else ""


def review_gate_errors(mode: dict[str, Any], text: str) -> list[str]:
    errors: list[str] = []
    verdict = _review_verdict(text)
    if verdict not in {"CLEAR", "CLEAR_WITH_CONCERNS", "BLOCK"}:
        errors.append("06-review.md verdict must be CLEAR, CLEAR_WITH_CONCERNS, or BLOCK")
    if not _has_section(text, r"Delivery\s+Scope\s+Check|delivery_scope_check"):
        errors.append("06-review.md is missing Delivery Scope Check")
    tdd_section = _extract_section(text, r"TDD\s+Gate")
    if not tdd_section:
        errors.append("06-review.md is missing TDD Gate")
    elif re.search(r"(?i)\bN/A\b|not\s+applicable", tdd_section):
        if not re.search(r"(?i)tdd[_\s-]*exception|orchestrator[_\s-]*waiver", tdd_section):
            errors.append("06-review.md TDD Gate declares N/A without an orchestrator waiver")
    if not _has_section(text, r"Checklist\s+Coverage"):
        errors.append("06-review.md is missing Checklist Coverage")
    if _is_ui_project(mode) and not _has_section(text, r"UI\s+Quality\s+Gate"):
        errors.append("06-review.md is missing UI Quality Gate for a UI project")
    if _is_ui_project(mode) and not ((_contract(mode).get("ui_quality") or {}).get("designer") or {}).get("result_note"):
        errors.append("G5 UI quality review requires designer participation before G6")
    return errors


def _record_review_evidence(mode: dict[str, Any]) -> None:
    path = review_path(mode)
    if not path.exists():
        raise StateError("06-review.md is missing; reviewer must write the review artifact before G5 can advance")
    text = path.read_text(encoding="utf-8")
    verdict = _review_verdict(text)
    _contract(mode)["review_evidence"] = {
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "recorded_at": utc_now(),
    }
    _contract(mode)["verdict"] = verdict


def _assert_g5_gate_ready(mode: dict[str, Any]) -> None:
    path = review_path(mode)
    if not path.exists():
        raise StateError("06-review.md is missing")
    text = path.read_text(encoding="utf-8")
    _record_review_evidence(mode)
    errors = review_gate_errors(mode, text)
    if errors:
        raise StateError("G5 review gate blocked: " + "; ".join(errors))


def _fresh_g4_contract(repair_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending",
        "execution_plan": None,
        "executor": None,
        "execution_evidence": None,
        "polish": None,
        "tdd": {},
        "repair_context": repair_context,
    }


def _fresh_g5_contract(repair_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending",
        "review_inputs": [],
        "reviewer": None,
        "review_evidence": None,
        "ui_quality": {"required": False, "designer": None},
        "verdict": None,
        "findings": [],
        "repair_context": repair_context,
    }


def _fresh_g6_contract(repair_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending",
        "verification_inputs": [],
        "verifier": None,
        "verification_evidence": None,
        "verdict": None,
        "delivery_confidence": None,
        "findings": [],
        "repair_context": repair_context,
    }


def _repair_loop_state(mode: dict[str, Any]) -> dict[str, Any]:
    state = mode.setdefault("repair_loop", {})
    if not isinstance(state, dict):
        state = {}
        mode["repair_loop"] = state
    state.setdefault("active_iteration", 0)
    state.setdefault("history", [])
    if not isinstance(state.get("history"), list):
        state["history"] = []
    return state


def _archive_repair_artifacts(mode: dict[str, Any], iteration: int) -> dict[str, Any]:
    archive_dir = Path(mode["run_dir"]) / "evidence" / f"g5-repair-{iteration:03d}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Any] = {}
    for name in ["05-execution.md", "06-review.md"]:
        source = _path_in_run(mode, name)
        record: dict[str, Any] = {"source": str(source.resolve()), "exists": source.exists()}
        if source.exists() and source.is_file():
            target = archive_dir / name
            shutil.copy2(source, target)
            record["archive"] = str(target.resolve())
            record["sha256"] = file_sha256(target)
        artifacts[name] = record
    return {"path": str(archive_dir.resolve()), "artifacts": artifacts}


def _reset_phase_subtree(mode: dict[str, Any], phase: str, *, active: bool = False) -> None:
    phase_event = event_by_id(mode, phase)
    phase_event["status"] = "active" if active else "pending"
    for key in ["completed_at", "blocked_reason"]:
        phase_event.pop(key, None)
    for child in child_events(mode, phase):
        child["status"] = "pending"
        for key in ["completed_at", "blocked_reason"]:
            child.pop(key, None)
    if active:
        event_by_id(mode, f"{phase}.START")["status"] = "active"


def _return_to_g4_repair(ws: Workspace, mode: dict[str, Any], verdict: str, note: str = "") -> dict[str, Any]:
    loop = _repair_loop_state(mode)
    iteration = int(loop.get("active_iteration") or 0) + 1
    archive = _archive_repair_artifacts(mode, iteration)
    current_contract = dict(_contract(mode))
    review = current_contract.get("review_evidence") or {}
    repair_context = {
        "iteration": iteration,
        "source_event": "G5.CHECK_REVIEW_GATE",
        "verdict": verdict,
        "reason": note.strip() or "G5 reviewer verdict BLOCK",
        "review_evidence": review,
        "archive": archive,
        "created_at": utc_now(),
    }
    loop["active_iteration"] = iteration
    loop["last_return_to"] = "G4"
    loop["history"].append(
        {
            "iteration": iteration,
            "verdict": verdict,
            "returned_to": "G4",
            "source_event": "G5.CHECK_REVIEW_GATE",
            "created_at": repair_context["created_at"],
            "review_evidence": review,
            "archive": archive,
        }
    )
    _trace_g5_hook(
        mode,
        f"G5.RETURN_TO_G4.iteration_{iteration}",
        f"verdict={verdict}",
        "G5.CHECK_REVIEW_GATE",
        "route blocked review back to G4 repair, then repeat G4-G5-G6",
        {"repair_context": repair_context},
    )
    _reset_phase_subtree(mode, "G4", active=True)
    _reset_phase_subtree(mode, "G5")
    _reset_phase_subtree(mode, "G6")
    mode["g4_contract"] = _fresh_g4_contract(repair_context)
    mode["g5_contract"] = _fresh_g5_contract(repair_context)
    mode["g6_contract"] = _fresh_g6_contract(repair_context)
    mode["stage"] = "execute"
    mode["status"] = "g5_block_returned_to_g4_repair"
    _set_orchestrator(
        mode,
        "G4.START",
        spawn_decision="none",
        spawn_status="not_required",
        expected_agent=None,
        instruction=f"G5 {verdict}; return to G4 repair iteration {iteration}, then repeat G4-G5-G6",
    )
    _set_inspector_not_required(mode, "G4.START")
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": "G5.CHECK_REVIEW_GATE",
        "verdict": verdict,
        "returned_to": "G4",
        "repair_iteration": iteration,
        "next_global_event": "G4",
        "next_event": "G4.START",
        "archive": archive["path"],
        "review": str(review_path(mode).resolve()),
    }


def _is_g4_complete(mode: dict[str, Any]) -> bool:
    try:
        return event_by_id(mode, "G4.COMPLETE").get("status") == "done"
    except KeyError:
        return False


def advance_g5(ws: Workspace, note: str = "") -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g5_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "review":
        raise StateError("G5 can only advance while stage=review")
    current = _active_g5_event(mode)
    event_id = str(current.get("id"))
    contract = _contract(mode)

    if event_id == "G5.START":
        if not _is_g4_complete(mode):
            raise StateError("G5.START requires G4.COMPLETE")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G5.LOAD_REVIEW_INPUTS":
        contract["review_inputs"] = _collect_review_inputs(mode)
        _trace_review_guidance(mode, event_id)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G5.CHECK_G4_COMPLETE":
        if not _is_g4_complete(mode) or (mode.get("g4_contract") or {}).get("status") != "done":
            raise StateError("G4 must be complete before G5 review")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G5.SPAWN_REVIEWER":
        raise StateError("G5.SPAWN_REVIEWER requires reviewer spawn/result through g5-trace")

    elif event_id == "G5.RECORD_REVIEW_EVIDENCE":
        if not (contract.get("reviewer") or {}).get("result_note"):
            raise StateError("G5.RECORD_REVIEW_EVIDENCE requires reviewer result")
        _record_review_evidence(mode)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G5.UI_QUALITY_REVIEW":
        if not _is_ui_project(mode):
            contract["ui_quality"] = {"required": False, "designer": None}
            next_event = _complete_current(mode, event_id, status="not_applicable")
        else:
            raise StateError("G5.UI_QUALITY_REVIEW requires designer spawn/result through g5-trace")

    elif event_id == "G5.CHECK_REVIEW_GATE":
        _assert_g5_gate_ready(mode)
        verdict = _contract(mode).get("verdict")
        if verdict == "BLOCK":
            return _return_to_g4_repair(ws, mode, str(verdict), note)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G5.COMPLETE":
        current["completed_at"] = utc_now()
        current["status"] = "done"
        _trace_g5_hook(mode, "G5.COMPLETE.record", "runtime recorded event result", "G5.COMPLETE", "record G5 completion")
        transition_to_phase(mode, "G6")
        _trace_g5_hook(mode, "G5.COMPLETE.next", "G5.COMPLETE=done", "G5.COMPLETE", "advance to G6")
        next_g6 = active_event(mode, "G6")
        next_id = str(next_g6.get("id") if next_g6 else "G6")
        _set_orchestrator(
            mode,
            next_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction="G5 complete; enter G6 verification",
        )
        _set_inspector_not_required(mode, next_id)
        contract["status"] = "done"
        mode["status"] = "verify_ready"
        save_mode(ws, mode)
        return {
            "ok": True,
            "event": "G5.COMPLETE",
            "next_global_event": "G6",
            "next_event": next_id,
            "review": str(review_path(mode).resolve()),
        }

    else:
        raise StateError(f"unsupported G5 event: {event_id}")

    mode["status"] = f"{event_id.lower()}_done"
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": event_id,
        "status": "done",
        "next_event": next_event.get("id") if next_event else None,
        "review": str(review_path(mode).resolve()),
    }


def run_g5_hook_trace_until_stage_gate(ws: Workspace, before_index: int | None = None) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g5_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "review":
        raise StateError("G5 hook-trace can only run while stage=review")
    if before_index is None:
        before_index = len(_hook_trace(mode))
    advanced: list[dict[str, Any]] = []

    while True:
        current = _active_g5_event(mode)
        event_id = str(current.get("id"))
        if event_id == "G5.SPAWN_REVIEWER":
            _ensure_g5_reviewer_required(mode)
            mode["status"] = "g5_review_waiting_for_reviewer_spawn"
            save_mode(ws, mode)
            return _g5_trace_result(mode, before_index, advanced)
        if event_id == "G5.UI_QUALITY_REVIEW" and _is_ui_project(mode):
            _ensure_designer_required(mode)
            mode["status"] = "g5_ui_quality_waiting_for_designer_spawn"
            save_mode(ws, mode)
            return _g5_trace_result(mode, before_index, advanced)
        result = advance_g5(ws)
        advanced.append({"event": result["event"], "next_event": result.get("next_event")})
        mode = load_mode(ws)
        assert mode is not None
        _ensure_g5_event_tree(mode)
        if mode.get("stage") != "review":
            return _g5_trace_result(mode, before_index, advanced)


def _expected_agent_for_event(event_id: str) -> str | None:
    if event_id == "G5.SPAWN_REVIEWER":
        return REVIEWER_AGENT
    if event_id == "G5.UI_QUALITY_REVIEW":
        return DESIGNER_AGENT
    return None


def apply_g5_hook_trace_signal(
    ws: Workspace,
    signal: str,
    note: str = "",
    *,
    agent: str = "",
    agent_id: str = "",
    severity: str = "",
) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g5_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    before_index = len(_hook_trace(mode))
    current = _active_g5_event(mode)
    event_id = str(current.get("id"))

    if signal == "review-finding":
        finding = {
            "ts": utc_now(),
            "event": event_id,
            "severity": severity.strip() or "concern",
            "note": note.strip(),
        }
        findings = _contract(mode).setdefault("findings", [])
        if not isinstance(findings, list):
            findings = []
            _contract(mode)["findings"] = findings
        findings.append(finding)
        _trace_g5_hook(mode, "G5.REVIEW_FINDING.record", note.strip() or "review finding", event_id, "record immediate reviewer finding", {"finding": finding})
        save_mode(ws, mode)
        return _g5_trace_result(mode, before_index, [])

    expected_agent = _expected_agent_for_event(event_id)
    if expected_agent is None:
        raise StateError(f"active G5 event is {event_id}; no agent signal is pending")
    agent_name = agent.strip() or expected_agent
    if agent_name != expected_agent:
        raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")

    if signal == "spawn-record":
        if expected_agent == REVIEWER_AGENT:
            _ensure_g5_reviewer_required(mode)
            scope = "review execution against G1-G4 artifacts and original SuperTeam reviewer rules"
        else:
            _ensure_designer_required(mode)
            scope = "participate in UI quality gate against Pencil and G3/G4 UI contracts"
        call_id = agent_id.strip() or f"{agent_name}-local"
        _record_agent_call(mode, event_id, agent_name, call_id, "spawned", scope)
        _trace_g5_hook(mode, f"{event_id}.spawn_record", f"agent_id={call_id}", event_id, f"record {agent_name} spawn", {"agent": agent_name, "agent_id": call_id, **agent_spawn_contract(agent_name)})
        _trace_g5_hook_once(mode, f"{event_id}.wait_result", f"waiting for {agent_name} result", event_id, f"wait for {agent_name} result")
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="waiting_result",
            expected_agent=expected_agent,
            instruction=f"wait for {agent_name} result",
        )
        _set_inspector_not_required(mode, event_id)
        mode["status"] = f"g5_{agent_name}_waiting_for_result"
        save_mode(ws, mode)
        return _g5_trace_result(mode, before_index, [])

    if signal == "agent-result":
        if not _has_agent_call(mode, event_id, expected_agent):
            raise StateError(f"{event_id} requires spawn_record before agent-result")
        if expected_agent == REVIEWER_AGENT:
            _record_review_evidence(mode)
        agent_call_id = _complete_agent_call(mode, event_id, expected_agent, note)
        _trace_g5_hook(mode, f"{event_id}.result_record", note.strip() or f"{expected_agent} completed", event_id, f"record {expected_agent} result", {"agent": expected_agent, "agent_id": agent_call_id})
        if expected_agent == REVIEWER_AGENT:
            _contract(mode)["reviewer"] = {
                "agent_id": agent_call_id,
                "result_note": note.strip(),
                "completed_at": utc_now(),
            }
        else:
            ui_quality = _contract(mode).setdefault("ui_quality", {"required": True, "designer": None})
            ui_quality["required"] = True
            ui_quality["designer"] = {
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
        mode["status"] = f"g5_{expected_agent}_result_recorded"
        save_mode(ws, mode)
        return run_g5_hook_trace_until_stage_gate(ws, before_index)

    raise StateError("signal must be one of: spawn-record, agent-result, review-finding")


def _g5_trace_result(mode: dict[str, Any], before_index: int, advanced: list[dict[str, Any]]) -> dict[str, Any]:
    current_event = None
    active_global = "G6" if mode.get("stage") == "verify" else "G4" if mode.get("stage") == "execute" else "G5"
    if mode.get("stage") == "review":
        current = active_event(mode, "G5") or blocked_event(mode, "G5")
        current_event = current.get("id") if current else None
    elif mode.get("stage") == "execute":
        current = active_event(mode, "G4") or blocked_event(mode, "G4")
        current_event = current.get("id") if current else None
    trace = _hook_trace(mode)
    return {
        "ok": True,
        "active_event": current_event,
        "active_global_event": active_global,
        "complete": _event(mode, "G5.COMPLETE").get("status") == "done",
        "advanced": advanced,
        "trace_hooks": [item.get("hook") for item in trace[before_index:] if isinstance(item, dict)],
        "events": child_events(mode, "G5"),
        "contract": _contract(mode),
        "repair_loop": mode.get("repair_loop"),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "review": str(review_path(mode).resolve()),
    }


def g5_status(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    _ensure_g5_event_tree(mode)
    save_mode(ws, mode)
    current = active_event(mode, "G5") or blocked_event(mode, "G5")
    return {
        "ok": True,
        "active_event": current.get("id") if current else None,
        "complete": _event(mode, "G5.COMPLETE").get("status") == "done",
        "events": child_events(mode, "G5"),
        "contract": _contract(mode),
        "hook_trace": _hook_trace(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "review": str(review_path(mode).resolve()),
    }
