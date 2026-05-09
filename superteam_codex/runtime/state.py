from __future__ import annotations

from pathlib import Path
from typing import Any

from .event_tree import (
    EVENT_STATUS_VALUES,
    EVENT_TERMINAL_STATUSES,
    G1_QUESTIONS,
    STAGE_TO_PHASE,
    create_event_tree,
    is_phase_complete,
    transition_to_phase,
    validate_event_tree,
)
from .workspace import PROJECT_SCHEMA, STATE_SCHEMA, Workspace, read_json, utc_now, write_json


STAGES = [
    "g1",
    "g2",
    "g3",
    "execute",
    "review",
    "verify",
    "finish",
]

ACTIVE_LIFECYCLES = {"running", "paused"}
G1_EVENT_STATUS_VALUES = EVENT_STATUS_VALUES
G1_TERMINAL_STATUSES = EVENT_TERMINAL_STATUSES


class StateError(RuntimeError):
    pass


def is_g1_complete(mode: dict[str, Any] | None) -> bool:
    if not isinstance(mode, dict):
        return False
    return is_phase_complete(mode, "G1")


def is_g2_complete(mode: dict[str, Any] | None) -> bool:
    if not isinstance(mode, dict):
        return False
    return is_phase_complete(mode, "G2")


def is_g3_complete(mode: dict[str, Any] | None) -> bool:
    if not isinstance(mode, dict):
        return False
    return is_phase_complete(mode, "G3")


def load_mode(ws: Workspace) -> dict[str, Any] | None:
    return read_json(ws.mode_path, None)


def load_project(ws: Workspace) -> dict[str, Any] | None:
    return read_json(ws.project_path, None)


def validate_mode(mode: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(mode, dict):
        return ["mode.json is missing or is not an object"]
    required = [
        "schema",
        "plugin",
        "mode",
        "project_lifecycle",
        "active_task_slug",
        "stage",
        "status",
        "project_root",
        "run_dir",
        "task",
        "event_tree",
    ]
    for key in required:
        if key not in mode:
            errors.append(f"missing mode field: {key}")
    errors.extend(validate_event_tree(mode.get("event_tree"), mode.get("stage")))
    if mode.get("schema") != STATE_SCHEMA:
        errors.append(f"unexpected mode schema: {mode.get('schema')!r}")
    if mode.get("plugin") != "superteam_codex":
        errors.append(f"unexpected plugin field: {mode.get('plugin')!r}")
    if mode.get("stage") not in STAGES:
        errors.append(f"unexpected stage: {mode.get('stage')!r}")
    if mode.get("project_lifecycle") not in {"running", "paused", "ended", "complete"}:
        errors.append(f"unexpected project_lifecycle: {mode.get('project_lifecycle')!r}")
    return errors


def create_mode(ws: Workspace, task: str, slug: str, run_dir: Path) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema": STATE_SCHEMA,
        "plugin": "superteam_codex",
        "mode": "active",
        "project_lifecycle": "running",
        "active_task_slug": slug,
        "stage": "g1",
        "status": "ready_for_project_definition",
        "project_root": str(ws.root),
        "run_dir": str(run_dir.resolve()),
        "task": task,
        "event_tree": create_event_tree(),
        "g1_approval": {
            "status": "pending",
            "approved_by": None,
            "approved_at": None,
            "note": "",
        },
        "g2_contract": {
            "status": "pending",
            "ui_authority": "pencil",
            "project_definition": None,
            "source_review": None,
            "ui": None,
            "design_decisions": [],
        },
        "g2_approval": {
            "status": "pending",
            "approved_by": None,
            "approved_at": None,
            "note": "",
        },
        "g3_contract": {
            "status": "pending",
            "deliverables": {},
            "implementation_surface": None,
            "ui_code_map": None,
            "layout_spec": None,
            "design_tokens": None,
            "interaction_state_map": None,
            "visual_acceptance": None,
            "work_items": [],
            "execution_plan": None,
        },
        "g3_approval": {
            "status": "pending",
            "approved_by": None,
            "approved_at": None,
            "note": "",
        },
        "g4_contract": {
            "status": "pending",
            "execution_plan": None,
            "executor": None,
            "execution_evidence": None,
            "polish": None,
            "tdd": {},
        },
        "g5_contract": {
            "status": "pending",
            "review_inputs": [],
            "reviewer": None,
            "review_evidence": None,
            "ui_quality": {"required": False, "designer": None},
            "verdict": None,
            "findings": [],
        },
        "g6_contract": {
            "status": "pending",
            "verification_inputs": [],
            "verifier": None,
            "verification_evidence": None,
            "verdict": None,
            "delivery_confidence": None,
            "findings": [],
        },
        "g7_contract": {
            "status": "pending",
            "finish_inputs": [],
            "inspector": None,
            "inspector_report": None,
            "writer": None,
            "finish_artifacts": {},
        },
        "orchestrator": {
            "role": "main_session_orchestrator",
            "spawn_decision": "not_required",
            "spawn_status": "not_required",
            "expected_agent": None,
            "active_event": "G1.Q1",
            "hook_instruction": "ask the active G1 question",
            "agent_calls": [],
        },
        "inspector": {
            "status": "not_run",
            "active_event": None,
            "checkpoint_required": False,
            "gate_check_report": {"status": "not_run", "checked_event": None, "findings": []},
            "trace_coverage": {"status": "not_run", "missing_events": [], "discrepancies": []},
        },
        "created_at": now,
        "updated_at": now,
        "guard": {
            "strict_stop_guard": True,
            "block_unmapped_ui_execution": True,
            "block_placeholder_product_ui": True,
            "block_nested_superteam_run": True,
        },
        "quality_gates": {
            "source_pack": "required",
            "pencil_design": "required_for_ui",
            "feature_ui_map": "required_for_ui",
            "execution_evidence": "required",
            "review_evidence": "required",
            "verification_evidence": "required",
        },
    }


def save_mode(ws: Workspace, mode: dict[str, Any]) -> None:
    mode["updated_at"] = utc_now()
    write_json(ws.mode_path, mode)


def create_or_update_project(ws: Workspace, slug: str, task: str) -> dict[str, Any]:
    now = utc_now()
    project = load_project(ws) or {
        "schema": PROJECT_SCHEMA,
        "plugin": "superteam_codex",
        "project_root": str(ws.root),
        "status": "in_progress",
        "created_at": now,
        "runs": [],
        "milestones": [],
    }
    project["updated_at"] = now
    project["current_run"] = slug
    if not any(run.get("slug") == slug for run in project.get("runs", [])):
        project.setdefault("runs", []).append(
            {
                "slug": slug,
                "task": task,
                "status": "running",
                "created_at": now,
            }
        )
    write_json(ws.project_path, project)
    return project


def set_lifecycle(ws: Workspace, lifecycle: str, status: str | None = None) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    mode["project_lifecycle"] = lifecycle
    if lifecycle in {"ended", "complete"}:
        mode["mode"] = "inactive"
    elif lifecycle in ACTIVE_LIFECYCLES:
        mode["mode"] = "active"
    if status is not None:
        mode["status"] = status
    save_mode(ws, mode)
    return mode


def set_stage(ws: Workspace, stage: str, status: str, force: bool = False) -> dict[str, Any]:
    if stage not in STAGES:
        raise StateError(f"unknown stage: {stage}")
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    assert mode is not None
    try:
        transition_to_phase(mode, STAGE_TO_PHASE[stage], force=force)
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    mode["status"] = status
    save_mode(ws, mode)
    return mode
