from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from .agent_registry import agent_spawn_contract, require_superteam_agent
from .event_tree import (
    G6_EVENT_IDS,
    active_event,
    blocked_event,
    child_events,
    event_by_id,
    g6_event_nodes,
    mark_active_event_terminal,
    transition_to_phase,
)
from .state import StateError, load_mode, save_mode, validate_mode
from .tdd import code_changing_work_items
from .workspace import Workspace, file_sha256, read_json, utc_now


VERIFIER_AGENT = require_superteam_agent("verifier", context="G6.SPAWN_VERIFIER")

VERIFICATION_INPUT_FILES = [
    "01-project-definition.md",
    "02-design.md",
    "04-plan.md",
    "05-execution.md",
    "06-review.md",
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


def _ensure_g6_event_tree(mode: dict[str, Any]) -> bool:
    existing = {item.get("id") for item in _event_tree_items(mode) if isinstance(item, dict)}
    if all(event_id in existing for event_id in G6_EVENT_IDS) and "G6.VERIFY_DELIVERY" not in existing:
        return False
    tree = [
        item
        for item in _event_tree_items(mode)
        if not (isinstance(item, dict) and item.get("phase") == "G6" and item.get("id") != "G6")
    ]
    mode["event_tree"] = tree + g6_event_nodes()
    if event_by_id(mode, "G6").get("status") == "active":
        event_by_id(mode, "G6.START")["status"] = "active"
    return True


def _event(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    try:
        return event_by_id(mode, event_id)
    except KeyError as exc:
        raise StateError(str(exc)) from exc


def _active_g6_event(mode: dict[str, Any]) -> dict[str, Any]:
    current = active_event(mode, "G6")
    if current is None:
        blocked = blocked_event(mode, "G6")
        if blocked is not None:
            raise StateError(f"G6 is blocked at {blocked.get('id')}: {blocked.get('blocked_reason', '')}")
        raise StateError("G6 must have exactly one active event before completion")
    return current


def _path_in_run(mode: dict[str, Any], name: str) -> Path:
    return Path(mode["run_dir"]) / name


def verification_path(mode: dict[str, Any]) -> Path:
    return _path_in_run(mode, "07-verification.md")


def _contract(mode: dict[str, Any]) -> dict[str, Any]:
    contract = mode.setdefault("g6_contract", {})
    contract.setdefault("status", "pending")
    contract.setdefault("verification_inputs", [])
    contract.setdefault("verifier", None)
    contract.setdefault("verification_evidence", None)
    contract.setdefault("verdict", None)
    contract.setdefault("delivery_confidence", None)
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


def _trace_g6_hook(
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


def _trace_g6_hook_once(
    mode: dict[str, Any],
    hook: str,
    trigger: str,
    event_id: str,
    instruction: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if not _has_hook(mode, hook):
        _trace_g6_hook(mode, hook, trigger, event_id, instruction, extra)


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
    _trace_g6_hook(mode, f"{event_id}.record", "runtime recorded event result", event_id, f"record {event_id}")
    if next_event is not None:
        next_id = str(next_event.get("id") or "")
        _trace_g6_hook(mode, f"{event_id}.next", f"{event_id}={status}", event_id, f"advance to {next_id}")
        _trace_g6_hook_once(mode, f"{next_id}.enter", f"{next_id}=active", next_id, "enter active G6 event")
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


def _collect_verification_inputs(mode: dict[str, Any]) -> list[dict[str, Any]]:
    return [_artifact_record(mode, name) for name in VERIFICATION_INPUT_FILES]


def _load_json_artifact(mode: dict[str, Any], name: str) -> dict[str, Any]:
    data = read_json(_path_in_run(mode, name), {})
    return data if isinstance(data, dict) else {}


def _implementation_plan(mode: dict[str, Any]) -> dict[str, Any]:
    return _load_json_artifact(mode, "implementation-plan.json")


def _ui_work_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    plan = _implementation_plan(mode)
    items = plan.get("work_items") if isinstance(plan.get("work_items"), list) else []
    return [item for item in items if isinstance(item, dict) and str(item.get("kind") or "").lower() == "ui"]


def _is_ui_project(mode: dict[str, Any]) -> bool:
    ui_map = _load_json_artifact(mode, "ui-code-map.json")
    mappings = ui_map.get("mappings") if isinstance(ui_map.get("mappings"), list) else []
    if ui_map.get("status") == "ok" and mappings:
        return True
    return bool(_ui_work_items(mode))


def _ui_guidance_payload(mode: dict[str, Any]) -> dict[str, Any]:
    return {
        "ui_code_map": _load_json_artifact(mode, "ui-code-map.json"),
        "layout_spec_status": _load_json_artifact(mode, "ui-layout-spec.json").get("status"),
        "design_tokens_status": _load_json_artifact(mode, "design-tokens.json").get("status"),
        "interaction_state_status": _load_json_artifact(mode, "interaction-state-map.json").get("status"),
        "visual_acceptance": _load_json_artifact(mode, "visual-acceptance.json"),
        "g5_ui_quality": ((mode.get("g5_contract") or {}).get("ui_quality") or {}),
    }


def _trace_verification_guidance(mode: dict[str, Any], event_id: str) -> None:
    inputs = _collect_verification_inputs(mode)
    _contract(mode)["verification_inputs"] = inputs
    missing = [item["name"] for item in inputs if not item.get("exists") and not item["name"].startswith("ui-")]
    repair_context = _contract(mode).get("repair_context")
    instruction = (
        "guide verifier before verification: use fresh commands and fresh evidence, compare G4 execution "
        "to G1/G2/G3/G5 artifacts, and issue only PASS, FAIL, or INCOMPLETE"
    )
    if isinstance(repair_context, dict) and repair_context:
        instruction = (
            f"{instruction}; this is repair iteration {repair_context.get('iteration')} after "
            f"G6 {repair_context.get('verdict')}, so verify the corrected items with fresh evidence"
        )
    _trace_g6_hook_once(
        mode,
        "G6.VERIFICATION_GUIDANCE.inputs",
        "before verifier spawn",
        event_id,
        instruction,
        {"verification_inputs": inputs, "missing_required_inputs": missing, "repair_context": repair_context},
    )
    plan = _implementation_plan(mode)
    _trace_g6_hook_once(
        mode,
        "G6.TEST_EVIDENCE_GUIDANCE",
        "before verifier spawn",
        event_id,
        "guide verifier to run or cite fresh test commands from implementation-plan verification_commands",
        {"work_items": plan.get("work_items") if isinstance(plan.get("work_items"), list) else []},
    )
    if _is_ui_project(mode):
        _trace_g6_hook_once(
            mode,
            "G6.UI_VERIFICATION_GUIDANCE",
            "ui_project=true",
            event_id,
            (
                "guide verifier before UI judgment: produce fresh visual/layout evidence against Pencil-derived "
                "ui-code-map, ui-layout-spec, design-tokens, interaction-state-map, visual-acceptance, and G5 UI review"
            ),
            {"ui_verification_guidance": _ui_guidance_payload(mode)},
        )
        for item in _ui_work_items(mode):
            frame_ids = [str(value) for value in item.get("frame_ids") or [] if str(value).strip()]
            frame_key = "_".join(frame_ids) if frame_ids else str(item.get("id") or "ui")
            _trace_g6_hook_once(
                mode,
                f"G6.UI_VERIFICATION_GUIDANCE.{frame_key}",
                f"ui_work_item={item.get('id')}",
                event_id,
                "guide fresh UI verification for this work item before final PASS/FAIL",
                {"ui_work_item": item},
            )


def _ensure_verifier_required(mode: dict[str, Any]) -> None:
    event_id = "G6.SPAWN_VERIFIER"
    _trace_g6_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter verifier spawn gate")
    _trace_verification_guidance(mode, event_id)
    _trace_g6_hook_once(
        mode,
        f"{event_id}.spawn_required",
        f"expected_agent={VERIFIER_AGENT}",
        event_id,
        "spawn verifier for independent fresh-evidence verdict; OR must not impersonate verifier",
        {"expected_agent": VERIFIER_AGENT, **agent_spawn_contract(VERIFIER_AGENT)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=VERIFIER_AGENT,
        instruction="spawn verifier; provide G6 guidance and original SuperTeam verifier rules before verification starts",
    )
    _set_inspector_not_required(mode, event_id)


def _verification_verdict(text: str) -> str | None:
    match = re.search(r"(?im)^\s*(?:verdict|status)\s*:\s*(PASS|FAIL|INCOMPLETE)\b", text)
    if match:
        return match.group(1)
    match = re.search(r"(?im)\b(PASS|FAIL|INCOMPLETE)\b", text)
    return match.group(1) if match else None


def _delivery_confidence(text: str) -> str | None:
    match = re.search(r"(?im)^\s*delivery_confidence\s*:\s*(high|medium|low)\b", text)
    return match.group(1).lower() if match else None


def _has_section(text: str, title_pattern: str) -> bool:
    return bool(re.search(rf"(?im)^#+\s*{title_pattern}\b", text) or re.search(title_pattern, text, re.IGNORECASE))


def verification_gate_errors(mode: dict[str, Any], text: str) -> list[str]:
    errors: list[str] = []
    verdict = _verification_verdict(text)
    if verdict not in {"PASS", "FAIL", "INCOMPLETE"}:
        errors.append("07-verification.md verdict must be PASS, FAIL, or INCOMPLETE")
    if not _has_section(text, r"Evidence\s+Summary|evidence_summary"):
        errors.append("07-verification.md is missing Evidence Summary")
    if not _has_section(text, r"Requirement\s+Status|requirement_status"):
        errors.append("07-verification.md is missing Requirement Status")
    if _delivery_confidence(text) is None:
        errors.append("07-verification.md is missing delivery_confidence: high|medium|low")
    try:
        code_items = code_changing_work_items(_implementation_plan(mode))
    except Exception:
        code_items = []
    if code_items and not _has_section(text, r"Test\s+Suite\s+Evidence|test_suite_evidence|Fresh\s+Test\s+Evidence"):
        errors.append("07-verification.md is missing fresh test suite evidence for code-changing work")
    if code_items and not re.search(r"(?im)\b(command|npm|pytest|unittest|cargo|go test|test)\b", text):
        errors.append("07-verification.md must include concrete fresh test command evidence")
    if _is_ui_project(mode) and not _has_section(text, r"UI\s+Evidence|Visual\s+Acceptance|Aesthetic\s+Contract\s+Evidence"):
        errors.append("07-verification.md is missing UI evidence for a UI project")
    return errors


def _record_verification_evidence(mode: dict[str, Any]) -> None:
    path = verification_path(mode)
    if not path.exists():
        raise StateError("07-verification.md is missing; verifier must write the verification artifact before G6 can advance")
    text = path.read_text(encoding="utf-8")
    _contract(mode)["verification_evidence"] = {
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "recorded_at": utc_now(),
    }
    _contract(mode)["verdict"] = _verification_verdict(text)
    _contract(mode)["delivery_confidence"] = _delivery_confidence(text)


def _assert_g6_gate_ready(mode: dict[str, Any]) -> None:
    path = verification_path(mode)
    if not path.exists():
        raise StateError("07-verification.md is missing")
    text = path.read_text(encoding="utf-8")
    _record_verification_evidence(mode)
    errors = verification_gate_errors(mode, text)
    if errors:
        raise StateError("G6 verification gate blocked: " + "; ".join(errors))


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
    archive_dir = Path(mode["run_dir"]) / "evidence" / f"g6-repair-{iteration:03d}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Any] = {}
    for name in ["05-execution.md", "06-review.md", "07-verification.md"]:
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
    verification = current_contract.get("verification_evidence") or {}
    repair_context = {
        "iteration": iteration,
        "source_event": "G6.CHECK_VERIFICATION_GATE",
        "verdict": verdict,
        "reason": note.strip() or f"G6 verifier verdict {verdict}",
        "verification_evidence": verification,
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
            "created_at": repair_context["created_at"],
            "verification_evidence": verification,
            "archive": archive,
        }
    )
    _trace_g6_hook(
        mode,
        f"G6.RETURN_TO_G4.iteration_{iteration}",
        f"verdict={verdict}",
        "G6.CHECK_VERIFICATION_GATE",
        "route failed verification back to G4 repair, then repeat G4-G5-G6",
        {"repair_context": repair_context},
    )
    _reset_phase_subtree(mode, "G4", active=True)
    _reset_phase_subtree(mode, "G5")
    _reset_phase_subtree(mode, "G6")
    mode["g4_contract"] = _fresh_g4_contract(repair_context)
    mode["g5_contract"] = _fresh_g5_contract(repair_context)
    mode["g6_contract"] = _fresh_g6_contract(repair_context)
    mode["stage"] = "execute"
    mode["status"] = f"g6_{verdict.lower()}_returned_to_g4_repair"
    _set_orchestrator(
        mode,
        "G4.START",
        spawn_decision="none",
        spawn_status="not_required",
        expected_agent=None,
        instruction=f"G6 {verdict}; return to G4 repair iteration {iteration}, then repeat G4-G5-G6",
    )
    _set_inspector_not_required(mode, "G4.START")
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": "G6.CHECK_VERIFICATION_GATE",
        "verdict": verdict,
        "returned_to": "G4",
        "repair_iteration": iteration,
        "next_global_event": "G4",
        "next_event": "G4.START",
        "archive": archive["path"],
        "verification": str(verification_path(mode).resolve()),
    }


def _is_g5_complete(mode: dict[str, Any]) -> bool:
    try:
        return event_by_id(mode, "G5.COMPLETE").get("status") == "done"
    except KeyError:
        return False


def advance_g6(ws: Workspace, note: str = "") -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g6_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "verify":
        raise StateError("G6 can only advance while stage=verify")
    current = _active_g6_event(mode)
    event_id = str(current.get("id"))
    contract = _contract(mode)

    if event_id == "G6.START":
        if not _is_g5_complete(mode):
            raise StateError("G6.START requires G5.COMPLETE")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G6.LOAD_VERIFICATION_INPUTS":
        contract["verification_inputs"] = _collect_verification_inputs(mode)
        _trace_verification_guidance(mode, event_id)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G6.CHECK_G5_COMPLETE":
        if not _is_g5_complete(mode) or (mode.get("g5_contract") or {}).get("status") != "done":
            raise StateError("G5 must be complete before G6 verification")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G6.SPAWN_VERIFIER":
        raise StateError("G6.SPAWN_VERIFIER requires verifier spawn/result through g6-trace")

    elif event_id == "G6.RECORD_VERIFICATION_EVIDENCE":
        if not (contract.get("verifier") or {}).get("result_note"):
            raise StateError("G6.RECORD_VERIFICATION_EVIDENCE requires verifier result")
        _record_verification_evidence(mode)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G6.CHECK_VERIFICATION_GATE":
        _assert_g6_gate_ready(mode)
        verdict = _contract(mode).get("verdict")
        if verdict in {"FAIL", "INCOMPLETE"}:
            return _return_to_g4_repair(ws, mode, str(verdict), note)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G6.COMPLETE":
        current["completed_at"] = utc_now()
        current["status"] = "done"
        _trace_g6_hook(mode, "G6.COMPLETE.record", "runtime recorded event result", "G6.COMPLETE", "record G6 completion")
        transition_to_phase(mode, "G7")
        _trace_g6_hook(mode, "G6.COMPLETE.next", "G6.COMPLETE=done", "G6.COMPLETE", "advance to G7")
        next_g7 = active_event(mode, "G7")
        next_id = str(next_g7.get("id") if next_g7 else "G7")
        _set_orchestrator(
            mode,
            next_id,
            spawn_decision="none",
            spawn_status="not_required",
            expected_agent=None,
            instruction="G6 complete with PASS; enter G7 finish",
        )
        _set_inspector_not_required(mode, next_id)
        contract["status"] = "done"
        mode["status"] = "finish_ready"
        save_mode(ws, mode)
        return {
            "ok": True,
            "event": "G6.COMPLETE",
            "next_global_event": "G7",
            "next_event": next_id,
            "verification": str(verification_path(mode).resolve()),
        }

    else:
        raise StateError(f"unsupported G6 event: {event_id}")

    mode["status"] = f"{event_id.lower()}_done"
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": event_id,
        "status": "done",
        "next_event": next_event.get("id") if next_event else None,
        "verification": str(verification_path(mode).resolve()),
    }


def run_g6_hook_trace_until_stage_gate(ws: Workspace, before_index: int | None = None) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g6_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "verify":
        raise StateError("G6 hook-trace can only run while stage=verify")
    if before_index is None:
        before_index = len(_hook_trace(mode))
    advanced: list[dict[str, Any]] = []

    while True:
        current = _active_g6_event(mode)
        event_id = str(current.get("id"))
        if event_id == "G6.SPAWN_VERIFIER":
            _ensure_verifier_required(mode)
            mode["status"] = "g6_verification_waiting_for_verifier_spawn"
            save_mode(ws, mode)
            return _g6_trace_result(mode, before_index, advanced)
        result = advance_g6(ws)
        advanced.append({"event": result["event"], "next_event": result.get("next_event")})
        mode = load_mode(ws)
        assert mode is not None
        _ensure_g6_event_tree(mode)
        if mode.get("stage") != "verify":
            return _g6_trace_result(mode, before_index, advanced)


def apply_g6_hook_trace_signal(
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
    _ensure_g6_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    before_index = len(_hook_trace(mode))
    current = _active_g6_event(mode)
    event_id = str(current.get("id"))

    if signal == "verification-finding":
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
        _trace_g6_hook(mode, "G6.VERIFICATION_FINDING.record", note.strip() or "verification finding", event_id, "record verifier finding", {"finding": finding})
        save_mode(ws, mode)
        return _g6_trace_result(mode, before_index, [])

    if event_id != "G6.SPAWN_VERIFIER":
        raise StateError(f"active G6 event is {event_id}; no verifier signal is pending")
    agent_name = agent.strip() or VERIFIER_AGENT
    if agent_name != VERIFIER_AGENT:
        raise StateError(f"{event_id} requires agent {VERIFIER_AGENT}, got {agent_name}")

    if signal == "spawn-record":
        _ensure_verifier_required(mode)
        call_id = agent_id.strip() or f"{agent_name}-local"
        _record_agent_call(
            mode,
            event_id,
            agent_name,
            call_id,
            "spawned",
            "verify delivery against G1-G5 artifacts using fresh evidence and original SuperTeam verifier rules",
        )
        _trace_g6_hook(mode, f"{event_id}.spawn_record", f"agent_id={call_id}", event_id, f"record {agent_name} spawn", {"agent": agent_name, "agent_id": call_id, **agent_spawn_contract(agent_name)})
        _trace_g6_hook_once(mode, f"{event_id}.wait_result", f"waiting for {agent_name} result", event_id, f"wait for {agent_name} result")
        _set_orchestrator(
            mode,
            event_id,
            spawn_decision="spawned",
            spawn_status="waiting_result",
            expected_agent=VERIFIER_AGENT,
            instruction=f"wait for {agent_name} result",
        )
        _set_inspector_not_required(mode, event_id)
        mode["status"] = "g6_verifier_waiting_for_result"
        save_mode(ws, mode)
        return _g6_trace_result(mode, before_index, [])

    if signal == "agent-result":
        if not _has_agent_call(mode, event_id, VERIFIER_AGENT):
            raise StateError(f"{event_id} requires spawn_record before agent-result")
        _record_verification_evidence(mode)
        agent_call_id = _complete_agent_call(mode, event_id, VERIFIER_AGENT, note)
        _trace_g6_hook(mode, f"{event_id}.result_record", note.strip() or "verifier completed", event_id, "record verifier result", {"agent": VERIFIER_AGENT, "agent_id": agent_call_id})
        _contract(mode)["verifier"] = {
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
            expected_agent=VERIFIER_AGENT,
            instruction=f"verifier completed; advance to {next_event.get('id') if next_event else 'next'}",
        )
        mode["status"] = "g6_verifier_result_recorded"
        save_mode(ws, mode)
        return run_g6_hook_trace_until_stage_gate(ws, before_index)

    raise StateError("signal must be one of: spawn-record, agent-result, verification-finding")


def _g6_trace_result(mode: dict[str, Any], before_index: int, advanced: list[dict[str, Any]]) -> dict[str, Any]:
    current_event = None
    active_global = "G7" if mode.get("stage") == "finish" else "G4" if mode.get("stage") == "execute" else "G6"
    if mode.get("stage") == "verify":
        current = active_event(mode, "G6") or blocked_event(mode, "G6")
        current_event = current.get("id") if current else None
    elif mode.get("stage") == "execute":
        current = active_event(mode, "G4") or blocked_event(mode, "G4")
        current_event = current.get("id") if current else None
    trace = _hook_trace(mode)
    return {
        "ok": True,
        "active_event": current_event,
        "active_global_event": active_global,
        "complete": _event(mode, "G6.COMPLETE").get("status") == "done",
        "advanced": advanced,
        "trace_hooks": [item.get("hook") for item in trace[before_index:] if isinstance(item, dict)],
        "events": child_events(mode, "G6"),
        "contract": _contract(mode),
        "repair_loop": mode.get("repair_loop"),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "verification": str(verification_path(mode).resolve()),
    }


def g6_status(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    _ensure_g6_event_tree(mode)
    save_mode(ws, mode)
    current = active_event(mode, "G6") or blocked_event(mode, "G6")
    return {
        "ok": True,
        "active_event": current.get("id") if current else None,
        "complete": _event(mode, "G6.COMPLETE").get("status") == "done",
        "events": child_events(mode, "G6"),
        "contract": _contract(mode),
        "hook_trace": _hook_trace(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "verification": str(verification_path(mode).resolve()),
    }
