from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .agent_registry import agent_spawn_contract, validate_spawn_policies
from .event_tree import (
    G3_EVENT_IDS,
    active_event,
    blocked_event,
    child_events,
    event_by_id,
    g3_event_nodes,
    mark_active_event_terminal,
    transition_to_phase,
)
from .state import StateError, is_g2_complete, is_g3_complete, load_mode, save_mode, validate_mode
from .workspace import Workspace, file_sha256, read_json, rel_to, utc_now, write_json, write_text


INSPECTOR_AGENT = "inspector"

G3_SPAWN_POLICIES: dict[str, dict[str, str]] = {
    "G3.SCAN_IMPLEMENTATION_SURFACE": {
        "agent": "architect",
        "scope": "scan project files, source manifest, and G1 technology constraints before G3 mapping",
    },
    "G3.MAP_PENCIL_TO_CODE_TARGETS": {
        "agent": "designer",
        "scope": "map Pencil frames and feature-ui-map entries to concrete code targets",
    },
    "G3.DRAFT_EXECUTION_PLAN": {
        "agent": "planner",
        "scope": "draft implementation-plan.json work items from ui-code-map and implementation surface",
    },
}
validate_spawn_policies(G3_SPAWN_POLICIES, context="G3_SPAWN_POLICIES")

G3_USER_GATE_EVENTS = {"G3.USER_APPROVAL"}


def _event_tree_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    tree = mode.setdefault("event_tree", [])
    if not isinstance(tree, list):
        raise StateError("mode.event_tree is missing or invalid")
    return tree


def _ensure_g3_event_tree(mode: dict[str, Any]) -> bool:
    existing = {item.get("id") for item in _event_tree_items(mode) if isinstance(item, dict)}
    if all(event_id in existing for event_id in G3_EVENT_IDS) and "G3.WORK_ITEMS" in existing:
        return False
    tree = [
        item
        for item in _event_tree_items(mode)
        if not (isinstance(item, dict) and item.get("phase") == "G3" and item.get("id") != "G3")
    ]
    mode["event_tree"] = tree + g3_event_nodes()
    if event_by_id(mode, "G3").get("status") == "active":
        event_by_id(mode, "G3.START")["status"] = "active"
    return True


def _event(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    try:
        return event_by_id(mode, event_id)
    except KeyError as exc:
        raise StateError(str(exc)) from exc


def _active_g3_event(mode: dict[str, Any]) -> dict[str, Any]:
    current = active_event(mode, "G3")
    if current is None:
        blocked = blocked_event(mode, "G3")
        if blocked is not None:
            raise StateError(f"G3 is blocked at {blocked.get('id')}: {blocked.get('blocked_reason', '')}")
        raise StateError("G3 must have exactly one active event before completion")
    return current


def _contract(mode: dict[str, Any]) -> dict[str, Any]:
    contract = mode.setdefault("g3_contract", {})
    contract.setdefault("status", "pending")
    contract.setdefault("deliverables", {})
    contract.setdefault("implementation_surface", None)
    contract.setdefault("ui_code_map", None)
    contract.setdefault("layout_spec", None)
    contract.setdefault("design_tokens", None)
    contract.setdefault("interaction_state_map", None)
    contract.setdefault("visual_acceptance", None)
    contract.setdefault("work_items", [])
    contract.setdefault("execution_plan", None)
    return contract


def _hook_trace(mode: dict[str, Any]) -> list[dict[str, Any]]:
    trace = mode.setdefault("hook_trace", [])
    if not isinstance(trace, list):
        trace = []
        mode["hook_trace"] = trace
    return trace


def _has_hook(mode: dict[str, Any], hook: str) -> bool:
    return any(isinstance(item, dict) and item.get("hook") == hook for item in _hook_trace(mode))


def _trace_g3_hook(
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


def _trace_g3_hook_once(
    mode: dict[str, Any],
    hook: str,
    trigger: str,
    event_id: str,
    instruction: str,
    extra: dict[str, Any] | None = None,
) -> None:
    if not _has_hook(mode, hook):
        _trace_g3_hook(mode, hook, trigger, event_id, instruction, extra)


def _orchestrator_state(mode: dict[str, Any]) -> dict[str, Any]:
    orch = mode.setdefault("orchestrator", {})
    orch.setdefault("role", "main_session_orchestrator")
    orch.setdefault("agent_calls", [])
    return orch


def _set_orchestrator(
    mode: dict[str, Any],
    event_id: str,
    *,
    spawn_decision: str,
    spawn_status: str,
    expected_agent: str | None,
    instruction: str,
) -> None:
    orch = _orchestrator_state(mode)
    orch["spawn_decision"] = spawn_decision
    orch["spawn_status"] = spawn_status
    orch["expected_agent"] = expected_agent
    orch["expected_agent_definition"] = agent_spawn_contract(expected_agent) if expected_agent else None
    orch["active_event"] = event_id
    orch["hook_instruction"] = instruction


def _clear_orchestrator(mode: dict[str, Any], event_id: str, instruction: str) -> None:
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="none",
        spawn_status="not_required",
        expected_agent=None,
        instruction=instruction,
    )


def _inspector_state(mode: dict[str, Any]) -> dict[str, Any]:
    inspector = mode.setdefault("inspector", {})
    inspector.setdefault("gate_check_report", {"status": "not_run", "checked_event": None, "findings": []})
    inspector.setdefault("trace_coverage", {"status": "not_run", "missing_events": [], "discrepancies": []})
    return inspector


def _set_inspector(
    mode: dict[str, Any],
    event_id: str,
    *,
    status: str,
    checkpoint_required: bool,
    agent_id: str | None = None,
) -> None:
    inspector = _inspector_state(mode)
    inspector["status"] = status
    inspector["active_event"] = event_id
    inspector["checkpoint_required"] = checkpoint_required
    inspector["agent_id"] = agent_id
    inspector["gate_check_report"] = {"status": "not_required", "checked_event": event_id, "findings": []}
    inspector["trace_coverage"] = {"status": "pass", "missing_events": [], "discrepancies": []}


def _record_agent_call(mode: dict[str, Any], event_id: str, role: str, agent_id: str, status: str, scope: str) -> None:
    calls = _orchestrator_state(mode).setdefault("agent_calls", [])
    calls.append(
        {
            "ts": utc_now(),
            "event": event_id,
            "role": role,
            "agent_id": agent_id,
            "scope": scope,
            "status": status,
            **agent_spawn_contract(role),
        }
    )


def _complete_agent_call(mode: dict[str, Any], event_id: str, role: str, note: str) -> None:
    for call in reversed(_orchestrator_state(mode).setdefault("agent_calls", [])):
        if call.get("event") == event_id and call.get("role") == role and call.get("status") == "spawned":
            call["status"] = "failed" if _note_indicates_failure(note) else "completed"
            call["completed_at"] = utc_now()
            call["result_note"] = note.strip()
            return


def _has_agent_call(mode: dict[str, Any], event_id: str, role: str) -> bool:
    return any(
        call.get("event") == event_id and call.get("role") == role and call.get("status") in {"spawned", "completed", "failed"}
        for call in _orchestrator_state(mode).get("agent_calls", [])
        if isinstance(call, dict)
    )


def _note_indicates_failure(note: str) -> bool:
    upper = note.strip().upper()
    return upper.startswith("FAIL:") or upper.startswith("FAIL ") or upper.startswith("INSPECTOR FAIL")


def _latest_agent_result_failed(mode: dict[str, Any], event_id: str, role: str) -> bool:
    for call in reversed(_orchestrator_state(mode).get("agent_calls", [])):
        if not isinstance(call, dict):
            continue
        if call.get("event") == event_id and call.get("role") == role:
            return call.get("status") == "failed" or _note_indicates_failure(str(call.get("result_note") or ""))
    return False


def _path_in_run(mode: dict[str, Any], name: str) -> Path:
    return Path(str(mode["run_dir"])) / name


def _load_json_artifact(mode: dict[str, Any], name: str) -> dict[str, Any]:
    data = read_json(_path_in_run(mode, name), {})
    return data if isinstance(data, dict) else {}


def _g1_answer(mode: dict[str, Any], event_id: str) -> str:
    try:
        return str(_event(mode, event_id).get("answer") or "").strip()
    except StateError:
        return ""


def _ui_required(mode: dict[str, Any]) -> bool:
    return bool(((mode.get("g2_contract") or {}).get("ui") or {}).get("required"))


def _block_current(mode: dict[str, Any], current: dict[str, Any], reason: str) -> None:
    current["status"] = "blocked"
    current["blocked_reason"] = reason
    current["blocked_at"] = utc_now()
    mode["status"] = f"{str(current.get('id')).lower()}_blocked"


def _complete_current(mode: dict[str, Any], event_id: str) -> dict[str, Any] | None:
    try:
        return mark_active_event_terminal(mode, event_id, "done")
    except ValueError as exc:
        raise StateError(str(exc)) from exc


def _trace_g3_transition(mode: dict[str, Any], event_id: str, next_event: dict[str, Any] | None, note: str = "") -> None:
    _trace_g3_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter active G3 event")
    _trace_g3_hook(mode, f"{event_id}.record", note.strip() or "runtime recorded event result", event_id, "record active G3 event result")
    if next_event is not None:
        next_id = str(next_event.get("id"))
        _trace_g3_hook(mode, f"{event_id}.next", f"{event_id}=done", event_id, f"advance to {next_id}")
        _trace_g3_hook_once(mode, f"{next_id}.enter", f"{next_id}=active", next_id, "enter active G3 event")


def _ensure_g3_spawn_required(mode: dict[str, Any], event_id: str) -> None:
    policy = G3_SPAWN_POLICIES[event_id]
    expected_agent = policy["agent"]
    _trace_g3_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, "enter active G3 event")
    _trace_g3_hook_once(
        mode,
        f"{event_id}.spawn_required",
        f"expected_agent={expected_agent}",
        event_id,
        f"spawn {expected_agent} for {event_id}",
        {"expected_agent": expected_agent, "scope": policy["scope"], **agent_spawn_contract(expected_agent)},
    )
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="required",
        spawn_status="pending",
        expected_agent=expected_agent,
        instruction=f"spawn {expected_agent}; main session must not complete {event_id} directly",
    )
    _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)


def _ensure_g3_user_gate_waiting(mode: dict[str, Any], event_id: str) -> None:
    _trace_g3_hook_once(mode, f"{event_id}.enter", f"{event_id}=active", event_id, f"enter user interaction gate {event_id}")
    _trace_g3_hook_once(mode, f"{event_id}.hold", "waiting for user approval", event_id, "hold at final G3 approval")
    _set_orchestrator(
        mode,
        event_id,
        spawn_decision="none",
        spawn_status="not_required",
        expected_agent=None,
        instruction="show 04-plan.md and wait for explicit G3 approval",
    )
    _set_inspector(mode, event_id, status="not_required", checkpoint_required=False)


def _require_g3_inspector(mode: dict[str, Any], event_id: str, instruction: str) -> None:
    _trace_g3_hook(
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
        instruction="spawn inspector; OR must not impersonate Inspector",
    )
    inspector = _inspector_state(mode)
    inspector["status"] = "waiting_for_spawn_record"
    inspector["active_event"] = event_id
    inspector["checkpoint_required"] = True
    inspector["agent_id"] = None
    inspector["pending_event"] = event_id


def _record_g3_inspector_spawn(mode: dict[str, Any], event_id: str, agent_id: str) -> None:
    call_id = agent_id.strip() or "inspector-local"
    _record_agent_call(mode, event_id, INSPECTOR_AGENT, call_id, "spawned", f"inspect {event_id} trace before advance")
    _trace_g3_hook(
        mode,
        f"{event_id}.inspector_spawn_record",
        f"agent_id={call_id}",
        event_id,
        "record inspector spawn",
        {"agent": INSPECTOR_AGENT, "agent_id": call_id, **agent_spawn_contract(INSPECTOR_AGENT)},
    )
    _trace_g3_hook_once(
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
    inspector = _inspector_state(mode)
    inspector["status"] = "waiting_for_agent_result"
    inspector["agent_id"] = call_id


def _record_g3_inspector_result(mode: dict[str, Any], event_id: str, note: str) -> None:
    inspector = _inspector_state(mode)
    agent_id = str(inspector.get("agent_id") or "")
    _complete_agent_call(mode, event_id, INSPECTOR_AGENT, note)
    _trace_g3_hook(
        mode,
        f"{event_id}.inspector_result_record",
        note.strip(),
        event_id,
        "record inspector result",
        {"agent": INSPECTOR_AGENT, "agent_id": agent_id},
    )
    _trace_g3_hook(
        mode,
        f"{event_id}.inspector_check",
        "inspector trace coverage pass",
        event_id,
        "Inspector agent completed trace check",
        {"agent": INSPECTOR_AGENT, "agent_id": agent_id},
    )
    inspector["status"] = "not_required"
    inspector["checkpoint_required"] = False
    inspector["gate_check_report"] = {"status": "pass", "checked_event": event_id, "findings": []}
    inspector["trace_coverage"] = {"status": "pass", "missing_events": [], "discrepancies": []}


def _extract_json_payload(note: str, marker: str) -> Any | None:
    idx = note.find(marker)
    if idx < 0:
        return None
    payload = note[idx + len(marker) :].strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug or fallback


def _page_slug(frame_id: str, frame_name: str) -> str:
    text = f"{frame_id} {frame_name}".lower()
    if "login" in text or "登录" in frame_name:
        return "login"
    if "roster" in text or "花名册" in frame_name or "员工" in frame_name:
        return "roster"
    return _slug(frame_name, frame_id)


def _page_path(slug: str) -> str:
    name = "".join(part.capitalize() for part in slug.split("-") if part) or "Page"
    return f"src/pages/{name}.tsx"


def _actions_from_features(features: list[str]) -> list[str]:
    pairs = [
        ("login", ["登录", "账号", "密码", "login"]),
        ("query", ["查询", "搜索", "筛选", "query", "search"]),
        ("create", ["新增", "添加", "create", "add"]),
        ("edit", ["编辑", "修改", "edit", "update"]),
        ("delete", ["删除", "delete", "remove"]),
    ]
    actions: list[str] = []
    joined = " ".join(features).lower()
    for action, tokens in pairs:
        if any(token.lower() in joined for token in tokens):
            actions.append(action)
    return actions or ["render"]


def _frame_lookup(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in inventory.get("frames", []) if isinstance(item, dict) and item.get("id")}


def _feature_entries(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = mapping.get("feature_mappings")
    if isinstance(explicit, list) and explicit:
        return [item for item in explicit if isinstance(item, dict)]
    entries: list[dict[str, Any]] = []
    for frame_id, hits in (mapping.get("references") or {}).items():
        entries.append({"feature": str(frame_id), "frame_id": str(frame_id), "references": hits})
    return entries


def _ui_component_targets(page_slug: str, actions: list[str]) -> list[str]:
    if page_slug == "login":
        return [
            "src/components/login/LoginCard.tsx",
            "src/components/login/LoginForm.tsx",
            "src/api/auth.ts",
        ]
    if page_slug == "roster":
        return [
            "src/components/roster/AppHeader.tsx",
            "src/components/roster/SidebarNav.tsx",
            "src/components/roster/RosterFilters.tsx",
            "src/components/roster/RosterStats.tsx",
            "src/components/roster/RosterToolbar.tsx",
            "src/components/roster/EmployeeFormModal.tsx",
            "src/components/roster/RosterTable.tsx",
            "src/components/roster/StatusTag.tsx",
            "src/api/employees.ts",
        ]
    base = "".join(part.capitalize() for part in page_slug.split("-") if part) or "Page"
    return [f"src/components/{base}View.tsx"]


def _api_targets_for_actions(actions: list[str]) -> list[str]:
    targets: list[str] = []
    if "login" in actions:
        targets.extend(["server/src/routes/auth.ts"])
    if any(action in actions for action in ["query", "create", "edit", "delete"]):
        targets.extend(["server/src/routes/employees.ts", "server/src/services/employeeService.ts"])
    return targets


def _data_targets_for_actions(actions: list[str]) -> list[str]:
    if any(action in actions for action in ["query", "create", "edit", "delete"]):
        return ["prisma/schema.prisma", "prisma/seed.ts", ".env"]
    return []


def _default_ui_code_map(mode: dict[str, Any], note: str = "") -> dict[str, Any]:
    inventory = _load_json_artifact(mode, "frame-inventory.json")
    feature_map = _load_json_artifact(mode, "feature-ui-map.json")
    frames = _frame_lookup(inventory)
    grouped: dict[str, dict[str, Any]] = {}
    for entry in _feature_entries(feature_map):
        frame_id = str(entry.get("frame_id") or "")
        if not frame_id:
            continue
        grouped.setdefault(frame_id, {"features": [], "references": []})
        feature = str(entry.get("feature") or frame_id).strip()
        if feature:
            grouped[frame_id]["features"].append(feature)
        if entry.get("references"):
            grouped[frame_id]["references"].extend(entry.get("references") or [])
    if not grouped:
        for frame_id, hits in (feature_map.get("references") or {}).items():
            grouped[str(frame_id)] = {"features": [str(frame_id)], "references": hits}

    mappings: list[dict[str, Any]] = []
    unmapped_features: list[str] = []
    for frame_id, payload in sorted(grouped.items()):
        frame = frames.get(frame_id, {})
        frame_name = str(frame.get("name") or frame_id)
        page_slug = _page_slug(frame_id, frame_name)
        features = [str(item) for item in payload.get("features", []) if str(item).strip()]
        actions = _actions_from_features(features)
        page = _page_path(page_slug)
        components = _ui_component_targets(page_slug, actions)
        api_targets = _api_targets_for_actions(actions)
        data_targets = _data_targets_for_actions(actions)
        code_targets = list(dict.fromkeys([page] + components + api_targets + data_targets))
        mappings.append(
            {
                "frame_id": frame_id,
                "frame_name": frame_name,
                "source_file": frame.get("source_file") or feature_map.get("authority_file") or "",
                "route": "/" if page_slug == "home" else f"/{page_slug}",
                "page": page,
                "components": components,
                "api_targets": api_targets,
                "data_targets": data_targets,
                "features": features,
                "actions": actions,
                "data_fields": _data_fields(mode, features),
                "source_refs": payload.get("references", []),
                "code_targets": code_targets,
            }
        )
    status = "ok" if mappings and not unmapped_features else "needs_mapping"
    return {
        "schema": "superteam_codex.ui_code_map.v1",
        "project_root": mode.get("project_root"),
        "status": status,
        "generated_from": {
            "pencil_authority_file": feature_map.get("authority_file") or "",
            "feature_ui_map": "feature-ui-map.json",
            "frame_inventory": "frame-inventory.json",
        },
        "mappings": mappings,
        "unmapped_features": unmapped_features,
        "note": note.strip(),
    }


def _data_fields(mode: dict[str, Any], features: list[str]) -> list[str]:
    text = (_g1_answer(mode, "G1.Q5") + " " + " ".join(features)).lower()
    if "员工" in text or "花名册" in text or "roster" in text:
        return ["employee.name", "employee.phone", "employee.position", "employee.status", "employee.hireDate"]
    if "login" in text or "登录" in text:
        return ["account", "password"]
    return []


def _contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)


# Override the legacy mojibake-sensitive helpers with Unicode-stable matching.
def _page_slug(frame_id: str, frame_name: str) -> str:
    text = f"{frame_id} {frame_name}".lower()
    if _contains_any(text, ["login", "\u767b\u5f55", "\u8d26\u53f7", "\u5bc6\u7801"]):
        return "login"
    if _contains_any(text, ["roster", "\u82b1\u540d\u518c", "\u5458\u5de5"]):
        return "roster"
    return _slug(frame_name, frame_id)


def _actions_from_features(features: list[str]) -> list[str]:
    pairs = [
        ("login", ["\u767b\u5f55", "\u8d26\u53f7", "\u5bc6\u7801", "login"]),
        ("query", ["\u67e5\u8be2", "\u641c\u7d22", "\u7b5b\u9009", "query", "search"]),
        ("create", ["\u65b0\u589e", "\u6dfb\u52a0", "create", "add"]),
        ("edit", ["\u7f16\u8f91", "\u4fee\u6539", "edit", "update"]),
        ("delete", ["\u5220\u9664", "delete", "remove"]),
    ]
    joined = " ".join(features).lower()
    actions = [action for action, tokens in pairs if any(token.lower() in joined for token in tokens)]
    return actions or ["render"]


def _data_fields(mode: dict[str, Any], features: list[str]) -> list[str]:
    feature_text = " ".join(features).lower()
    if _contains_any(feature_text, ["login", "\u767b\u5f55", "\u8d26\u53f7", "\u5bc6\u7801"]):
        return ["account", "password"]
    text = (_g1_answer(mode, "G1.Q5") + " " + feature_text).lower()
    if _contains_any(text, ["roster", "\u82b1\u540d\u518c", "\u5458\u5de5"]):
        return ["employee.name", "employee.phone", "employee.position", "employee.status", "employee.hireDate"]
    return []


def _write_ui_code_map(mode: dict[str, Any], mapping: dict[str, Any]) -> None:
    write_json(_path_in_run(mode, "ui-code-map.json"), mapping)
    lines = ["# UI Code Map", "", f"Status: {mapping.get('status')}", ""]
    for item in mapping.get("mappings", []):
        lines.extend(
            [
                f"## {item.get('frame_id')} - {item.get('frame_name')}",
                "",
                f"- source_file: `{item.get('source_file')}`",
                f"- route: `{item.get('route')}`",
                f"- page: `{item.get('page')}`",
                f"- code_targets: {', '.join(f'`{target}`' for target in item.get('code_targets', []))}",
                f"- features: {', '.join(str(feature) for feature in item.get('features', []))}",
                "",
            ]
        )
    write_text(_path_in_run(mode, "ui-code-map.md"), "\n".join(lines).rstrip() + "\n")


def _pencil_source_files(mode: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = _load_json_artifact(mode, "source-manifest.json")
    return [item for item in manifest.get("files", []) if isinstance(item, dict) and item.get("kind") == "pencil"]


def _read_pencil_documents(mode: dict[str, Any]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for source in _pencil_source_files(mode):
        path = Path(str(source.get("absolute_path") or ""))
        if not path.exists():
            continue
        data = read_json(path, {})
        if isinstance(data, dict):
            docs.append({"source": source, "document": data})
    return docs


def _walk_pencil_node(node: dict[str, Any], source_file: str, path: str = "") -> list[dict[str, Any]]:
    node_id = str(node.get("id") or "")
    name = str(node.get("name") or node_id)
    current_path = f"{path}/{node_id}".strip("/") if node_id else path
    records = [
        {
            "id": node_id,
            "name": name,
            "type": node.get("type"),
            "path": current_path,
            "source_file": source_file,
            "raw": node,
        }
    ]
    for child in node.get("children", []) or []:
        if isinstance(child, dict):
            records.extend(_walk_pencil_node(child, source_file, current_path))
    return records


def _raw_pencil_node_index(mode: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in _read_pencil_documents(mode):
        source = item["source"].get("path") or ""
        document = item["document"]
        for record in _walk_pencil_node(document, str(source)):
            if record.get("id"):
                index[str(record["id"])] = record
    return index


def _pick_raw(raw: dict[str, Any], names: list[str], default: Any = None) -> Any:
    for name in names:
        if name in raw:
            return raw.get(name)
    return default


def _layout_from_frame(frame: dict[str, Any], raw_record: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (raw_record or {}).get("raw") or {}
    return {
        "frame_id": frame.get("id"),
        "frame_name": frame.get("name"),
        "source_file": frame.get("source_file"),
        "path": frame.get("path"),
        "bounds": {
            "x": _pick_raw(raw, ["x", "left"], None),
            "y": _pick_raw(raw, ["y", "top"], None),
            "width": frame.get("width", _pick_raw(raw, ["width", "w"], None)),
            "height": frame.get("height", _pick_raw(raw, ["height", "h"], None)),
        },
        "layout": {
            "direction": _pick_raw(raw, ["layoutMode", "direction", "flow"], None),
            "align_items": _pick_raw(raw, ["alignItems", "align_items"], None),
            "justify_content": _pick_raw(raw, ["justifyContent", "justify_content"], None),
            "padding": _pick_raw(raw, ["padding", "paddingLeft"], None),
            "gap": _pick_raw(raw, ["gap", "itemSpacing"], None),
        },
        "children": [child.get("id") for child in raw.get("children", []) if isinstance(child, dict) and child.get("id")],
    }


def _default_layout_spec(mode: dict[str, Any]) -> dict[str, Any]:
    inventory = _load_json_artifact(mode, "frame-inventory.json")
    ui_map = _load_json_artifact(mode, "ui-code-map.json")
    raw_index = _raw_pencil_node_index(mode)
    mapped_frame_ids = {str(item.get("frame_id")) for item in ui_map.get("mappings", []) if item.get("frame_id")}
    frames = [item for item in inventory.get("frames", []) if isinstance(item, dict)]
    frame_specs = [_layout_from_frame(frame, raw_index.get(str(frame.get("id")))) for frame in frames]
    top_level = [spec for spec in frame_specs if str(spec.get("frame_id")) in mapped_frame_ids]
    return {
        "schema": "superteam_codex.ui_layout_spec.v1",
        "project_root": mode.get("project_root"),
        "status": "ok" if top_level else "needs_mapping",
        "generated_from": {
            "frame_inventory": "frame-inventory.json",
            "ui_code_map": "ui-code-map.json",
            "pencil_files": [item.get("path") for item in _pencil_source_files(mode)],
        },
        "top_level_frames": top_level,
        "frames": frame_specs,
    }


def _write_layout_spec(mode: dict[str, Any], spec: dict[str, Any]) -> None:
    write_json(_path_in_run(mode, "ui-layout-spec.json"), spec)
    lines = ["# UI Layout Spec", "", f"Status: {spec.get('status')}", ""]
    for item in spec.get("top_level_frames", []):
        bounds = item.get("bounds") or {}
        lines.append(f"- `{item.get('frame_id')}` {item.get('frame_name')} width={bounds.get('width')} height={bounds.get('height')}")
    write_text(_path_in_run(mode, "ui-layout-spec.md"), "\n".join(lines).rstrip() + "\n")


def _collect_token_values(raw: Any, tokens: dict[str, set[str]]) -> None:
    if isinstance(raw, dict):
        for key, value in raw.items():
            lower = str(key).lower()
            if any(part in lower for part in ["color", "fill", "background", "stroke"]):
                tokens.setdefault("colors", set()).add(str(value))
            elif any(part in lower for part in ["font", "fontsize", "font_size"]):
                tokens.setdefault("typography", set()).add(str(value))
            elif "radius" in lower or "corner" in lower:
                tokens.setdefault("radii", set()).add(str(value))
            elif "shadow" in lower:
                tokens.setdefault("shadows", set()).add(str(value))
            _collect_token_values(value, tokens)
    elif isinstance(raw, list):
        for item in raw:
            _collect_token_values(item, tokens)


def _default_design_tokens(mode: dict[str, Any]) -> dict[str, Any]:
    tokens: dict[str, set[str]] = {"colors": set(), "typography": set(), "radii": set(), "shadows": set()}
    for item in _read_pencil_documents(mode):
        _collect_token_values(item["document"], tokens)
    normalized = {key: sorted(value) for key, value in tokens.items()}
    return {
        "schema": "superteam_codex.design_tokens.v1",
        "project_root": mode.get("project_root"),
        "status": "ok",
        "generated_from": {
            "pencil_files": [item.get("path") for item in _pencil_source_files(mode)],
            "frame_inventory": "frame-inventory.json",
        },
        "tokens": normalized,
        "fallback_rule": "If a token is absent from raw Pencil JSON, G4 must match the Pencil export and G6 visual acceptance instead of inventing a new style.",
    }


def _write_design_tokens(mode: dict[str, Any], tokens: dict[str, Any]) -> None:
    write_json(_path_in_run(mode, "design-tokens.json"), tokens)
    lines = ["# Design Tokens", "", f"Status: {tokens.get('status')}", ""]
    for key, values in (tokens.get("tokens") or {}).items():
        lines.append(f"- {key}: {len(values)}")
    write_text(_path_in_run(mode, "design-tokens.md"), "\n".join(lines).rstrip() + "\n")


def _state_names_for_actions(actions: list[str]) -> list[str]:
    states = ["default", "hover", "focus", "disabled", "loading"]
    if any(action in actions for action in ["query", "search"]):
        states.extend(["empty", "filtered", "error"])
    if any(action in actions for action in ["create", "edit"]):
        states.extend(["modal_open", "form_validation_error", "submit_success"])
    if "delete" in actions:
        states.extend(["delete_confirm", "delete_cancelled"])
    return list(dict.fromkeys(states))


def _default_interaction_state_map(mode: dict[str, Any]) -> dict[str, Any]:
    ui_map = _load_json_artifact(mode, "ui-code-map.json")
    pages = []
    for item in ui_map.get("mappings", []):
        actions = [str(action) for action in item.get("actions", [])]
        pages.append(
            {
                "frame_id": item.get("frame_id"),
                "route": item.get("route"),
                "page": item.get("page"),
                "actions": actions,
                "states": _state_names_for_actions(actions),
            }
        )
    return {
        "schema": "superteam_codex.interaction_state_map.v1",
        "project_root": mode.get("project_root"),
        "status": "ok" if pages else "needs_mapping",
        "generated_from": {"ui_code_map": "ui-code-map.json", "g1_features": "G1.Q3", "g1_data": "G1.Q5"},
        "pages": pages,
    }


def _write_interaction_state_map(mode: dict[str, Any], mapping: dict[str, Any]) -> None:
    write_json(_path_in_run(mode, "interaction-state-map.json"), mapping)
    lines = ["# Interaction State Map", "", f"Status: {mapping.get('status')}", ""]
    for page in mapping.get("pages", []):
        lines.append(f"- `{page.get('frame_id')}` states: {', '.join(page.get('states', []))}")
    write_text(_path_in_run(mode, "interaction-state-map.md"), "\n".join(lines).rstrip() + "\n")


def _default_visual_acceptance(mode: dict[str, Any]) -> dict[str, Any]:
    ui_map = _load_json_artifact(mode, "ui-code-map.json")
    checks = []
    for item in ui_map.get("mappings", []):
        frame_id = str(item.get("frame_id") or "")
        checks.append(
            {
                "frame_id": frame_id,
                "page": item.get("page"),
                "route": item.get("route"),
                "viewport": {"width": 1440, "height": 900},
                "pencil_reference": {
                    "source_file": item.get("source_file"),
                    "frame_id": frame_id,
                    "export_required": True,
                },
                "implementation_screenshot": f"evidence/g6/{frame_id}-implementation.png",
                "comparison": {
                    "mode": "screenshot_and_layout",
                    "max_pixel_diff_ratio": 0.02,
                    "must_match": ["bounds", "text", "spacing", "alignment", "colors"],
                    "manual_review_required": True,
                },
            }
        )
    return {
        "schema": "superteam_codex.visual_acceptance.v1",
        "project_root": mode.get("project_root"),
        "status": "ok" if checks else "needs_mapping",
        "generated_from": {
            "ui_code_map": "ui-code-map.json",
            "ui_layout_spec": "ui-layout-spec.json",
            "design_tokens": "design-tokens.json",
        },
        "checks": checks,
    }


def _write_visual_acceptance(mode: dict[str, Any], acceptance: dict[str, Any]) -> None:
    write_json(_path_in_run(mode, "visual-acceptance.json"), acceptance)
    lines = ["# Visual Acceptance", "", f"Status: {acceptance.get('status')}", ""]
    for check in acceptance.get("checks", []):
        viewport = check.get("viewport") or {}
        lines.append(f"- `{check.get('frame_id')}` viewport={viewport.get('width')}x{viewport.get('height')} route=`{check.get('route')}`")
    write_text(_path_in_run(mode, "visual-acceptance.md"), "\n".join(lines).rstrip() + "\n")


def _js_stack_required(mode: dict[str, Any]) -> bool:
    text = _g1_answer(mode, "G1.Q7").lower()
    return any(token in text for token in ["react", "vite", "typescript", "node", "prisma", "sqlite", "ant design"])


def _default_verification_commands(mode: dict[str, Any]) -> list[str]:
    if _js_stack_required(mode):
        return [
            "npm install",
            "npm run typecheck",
            "npm run build",
            "npx prisma validate",
            "npx prisma migrate dev --name init",
            "npm run test:api",
        ]
    package_json = Path(str(mode.get("project_root") or "")) / "package.json"
    return ["npm run build", "npm test"] if package_json.exists() else ["python -m compileall ."]


def _project_has_scaffold(mode: dict[str, Any]) -> bool:
    root = Path(str(mode.get("project_root") or ""))
    required = ["package.json", "src", "server", "prisma"]
    return all((root / item).exists() for item in required)


def _scaffold_targets() -> list[str]:
    return [
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "server/src/index.ts",
        "server/src/prisma.ts",
        "prisma/schema.prisma",
        "prisma/seed.ts",
        ".env",
    ]


def _backend_data_targets(actions: list[str]) -> list[str]:
    targets = [
        "server/src/index.ts",
        "server/src/prisma.ts",
        "server/src/routes/auth.ts",
        "server/src/routes/employees.ts",
        "server/src/services/employeeService.ts",
        "prisma/schema.prisma",
        "prisma/seed.ts",
        ".env",
    ]
    return list(dict.fromkeys(targets))


def _default_implementation_surface(mode: dict[str, Any], note: str = "") -> dict[str, Any]:
    manifest = _load_json_artifact(mode, "source-manifest.json")
    return {
        "status": "ok",
        "technology_constraints": _g1_answer(mode, "G1.Q7"),
        "source_files": manifest.get("files", []),
        "default_code_roots": ["src/pages", "src/components", "src/api", "server", "prisma"],
        "project_has_scaffold": _project_has_scaffold(mode),
        "verification_commands": _default_verification_commands(mode),
        "note": note.strip(),
    }


def _default_work_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    contract = _contract(mode)
    ui_map = contract.get("ui_code_map") or _load_json_artifact(mode, "ui-code-map.json")
    surface = contract.get("implementation_surface") or _default_implementation_surface(mode)
    commands = surface.get("verification_commands") or ["npm run build"]
    items: list[dict[str, Any]] = []
    for index, mapping in enumerate(ui_map.get("mappings", []), start=1):
        frame_id = str(mapping.get("frame_id") or "")
        title = f"实现 {mapping.get('frame_name') or frame_id}"
        items.append(
            {
                "id": f"WI-{index:03d}",
                "kind": "ui",
                "title": title,
                "features": mapping.get("features", []),
                "frame_ids": [frame_id],
                "source_refs": mapping.get("source_refs", []),
                "code_targets": list(dict.fromkeys((mapping.get("code_targets") or []) + [mapping.get("page")] + (mapping.get("components") or []))),
                "actions": mapping.get("actions", []),
                "data_fields": mapping.get("data_fields", []),
                "spec_refs": {
                    "layout": f"ui-layout-spec.json#frames.{frame_id}",
                    "tokens": "design-tokens.json",
                    "states": f"interaction-state-map.json#pages.{frame_id}",
                    "visual_acceptance": f"visual-acceptance.json#checks.{frame_id}",
                },
                "acceptance_checks": [
                    f"UI matches Pencil frame `{frame_id}` using ui-layout-spec.json",
                    "Styles use design-tokens.json or the Pencil export fallback rule",
                    "All required interaction states are implemented",
                    "Final screenshots satisfy visual-acceptance.json",
                    "All mapped actions are implemented or intentionally deferred in the plan",
                ],
                "verification_commands": commands,
            }
        )
    if _g1_answer(mode, "G1.Q5") and "不需要" not in _g1_answer(mode, "G1.Q5"):
        items.append(
            {
                "id": f"WI-{len(items) + 1:03d}",
                "kind": "data",
                "title": "实现数据模型与基础 API",
                "features": [_g1_answer(mode, "G1.Q5")],
                "frame_ids": ["NO_UI"],
                "source_refs": [{"event": "G1.Q5"}],
                "code_targets": ["prisma/schema.prisma", "server/routes/employees.ts"],
                "actions": ["query", "create", "edit", "delete"],
                "data_fields": _data_fields(mode, []),
                "acceptance_checks": ["Roster data can be created, edited, deleted, and queried"],
                "verification_commands": commands,
            }
        )
    return items


def _default_work_items(mode: dict[str, Any]) -> list[dict[str, Any]]:
    contract = _contract(mode)
    ui_map = contract.get("ui_code_map") or _load_json_artifact(mode, "ui-code-map.json")
    surface = contract.get("implementation_surface") or _default_implementation_surface(mode)
    commands = _default_verification_commands(mode) if _js_stack_required(mode) else surface.get("verification_commands") or ["npm run build"]
    mappings = [item for item in ui_map.get("mappings", []) if isinstance(item, dict)]
    all_actions = list(dict.fromkeys(action for mapping in mappings for action in mapping.get("actions", []) if isinstance(action, str)))
    items: list[dict[str, Any]] = []

    if _js_stack_required(mode) and not _project_has_scaffold(mode):
        items.append(
            {
                "id": "WI-001",
                "kind": "scaffold",
                "title": "初始化 React/Vite/Node/Prisma 项目骨架",
                "features": [_g1_answer(mode, "G1.Q7")],
                "frame_ids": ["NO_UI"],
                "source_refs": [{"event": "G1.Q7"}],
                "code_targets": _scaffold_targets(),
                "actions": ["setup"],
                "data_fields": [],
                "acceptance_checks": [
                    "Root package scripts exist for typecheck, build, API smoke test, and Prisma validation",
                    "React/Vite/TypeScript/Ant Design app shell exists with route mounting",
                    "Node API bootstrap and Prisma client bootstrap exist",
                    "SQLite datasource and Prisma schema are initialized",
                ],
                "verification_commands": commands,
            }
        )

    data_answer = _g1_answer(mode, "G1.Q5")
    if data_answer and not _contains_any(data_answer, ["\u4e0d\u9700\u8981", "no"]):
        items.append(
            {
                "id": f"WI-{len(items) + 1:03d}",
                "kind": "data_api",
                "title": "实现员工花名册数据模型与 API",
                "features": [data_answer],
                "frame_ids": ["NO_UI"],
                "source_refs": [{"event": "G1.Q5"}, {"artifact": "ui-code-map.json"}],
                "code_targets": _backend_data_targets(all_actions),
                "actions": all_actions or ["query", "create", "edit", "delete"],
                "data_fields": _data_fields(mode, ["员工花名册"]),
                "acceptance_checks": [
                    "Employee model supports create, edit, delete, query, and status fields",
                    "Auth login endpoint exists for the login UI action",
                    "Employees CRUD and stats endpoints exist for the roster UI actions",
                    "Prisma schema validates and SQLite migration/seed path is defined",
                ],
                "verification_commands": commands,
            }
        )

    for mapping in mappings:
        frame_id = str(mapping.get("frame_id") or "")
        frame_name = str(mapping.get("frame_name") or frame_id)
        actions = [str(action) for action in mapping.get("actions", []) if str(action).strip()]
        page_slug = _page_slug(frame_id, frame_name)
        component_targets = _ui_component_targets(page_slug, actions)
        code_targets = list(
            dict.fromkeys(
                ["src/App.tsx"]
                + (mapping.get("code_targets") or [])
                + [mapping.get("page")]
                + (mapping.get("components") or [])
                + component_targets
                + _api_targets_for_actions(actions)
            )
        )
        items.append(
            {
                "id": f"WI-{len(items) + 1:03d}",
                "kind": "ui",
                "title": f"实现 {frame_name}",
                "features": mapping.get("features", []),
                "frame_ids": [frame_id],
                "source_refs": mapping.get("source_refs", [])
                or [{"artifact": "ui-code-map.json", "frame_id": frame_id}, {"artifact": "ui-layout-spec.json", "frame_id": frame_id}],
                "code_targets": [target for target in code_targets if target],
                "actions": actions,
                "data_fields": mapping.get("data_fields", []),
                "spec_refs": {
                    "layout": f"ui-layout-spec.json#frames.{frame_id}",
                    "tokens": "design-tokens.json",
                    "states": f"interaction-state-map.json#pages.{frame_id}",
                    "visual_acceptance": f"visual-acceptance.json#checks.{frame_id}",
                },
                "acceptance_checks": [
                    f"UI matches Pencil frame `{frame_id}` using ui-layout-spec.json",
                    "Styles use design-tokens.json or the Pencil export fallback rule",
                    "All required interaction states are implemented",
                    "Final screenshots satisfy visual-acceptance.json",
                    "All mapped actions are implemented or intentionally deferred in the plan",
                ],
                "verification_commands": commands,
            }
        )
    return items


def _write_implementation_plan(mode: dict[str, Any], items: list[dict[str, Any]], note: str = "") -> dict[str, Any]:
    plan = {
        "schema": "superteam_codex.implementation_plan.v1",
        "project_root": mode.get("project_root"),
        "status": "ok" if items else "empty",
        "work_items": items,
        "note": note.strip(),
    }
    write_json(_path_in_run(mode, "implementation-plan.json"), plan)
    return plan


def _execution_items_need_regeneration(mode: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    if not items:
        return True
    if not _js_stack_required(mode):
        return False
    kinds = {str(item.get("kind") or "") for item in items if isinstance(item, dict)}
    if not _project_has_scaffold(mode) and "scaffold" not in kinds:
        return True
    if "data_api" not in kinds:
        return True
    commands = {
        command
        for item in items
        if isinstance(item, dict)
        for command in item.get("verification_commands", [])
        if isinstance(command, str)
    }
    if "python -m compileall ." in commands:
        return True
    for command in ["npm run typecheck", "npm run build", "npx prisma validate"]:
        if command not in commands:
            return True
    targets = {
        target
        for item in items
        if isinstance(item, dict)
        for target in item.get("code_targets", [])
        if isinstance(target, str)
    }
    required_targets = {
        "package.json",
        "src/App.tsx",
        "src/api/auth.ts",
        "src/api/employees.ts",
        "server/src/index.ts",
        "server/src/prisma.ts",
        "server/src/routes/auth.ts",
        "server/src/routes/employees.ts",
        "prisma/schema.prisma",
    }
    return not required_targets.issubset(targets)


def _materialize_execution_plan_for_retry(mode: dict[str, Any], note: str = "") -> dict[str, Any]:
    contract = _contract(mode)
    items = _default_work_items(mode)
    plan = _write_implementation_plan(mode, items, note)
    contract["work_items"] = items
    contract["execution_plan"] = plan
    contract["deliverables"]["implementation_plan"] = str(_path_in_run(mode, "implementation-plan.json").resolve())
    _materialize_work_item_tree(mode, items)
    return plan


def _materialize_work_item_tree(mode: dict[str, Any], items: list[dict[str, Any]]) -> None:
    tree = [
        item
        for item in _event_tree_items(mode)
        if not (isinstance(item, dict) and item.get("parent") == "G3.WORK_ITEMS" and item.get("kind") == "work_item")
    ]
    mode["event_tree"] = tree
    group = _event(mode, "G3.WORK_ITEMS")
    group["status"] = "done"
    group["answer_ref"] = "implementation-plan.json#work_items"
    for index, item in enumerate(items, start=1):
        mode["event_tree"].append(
            {
                "id": f"G3.WORK_ITEMS.ITEM_{index:03d}",
                "parent": "G3.WORK_ITEMS",
                "phase": "G3",
                "kind": "work_item",
                "status": "done",
                "title": str(item.get("title") or item.get("id") or f"Work item {index}"),
                "requires": [],
                "next": None,
                "authority": ["implementation-plan.json", "ui-code-map.json"],
                "artifact": "04-plan.md",
                "hook_policy": "planned_g4_work_item",
                "requires_answer": False,
                "answer": "",
                "answer_ref": f"implementation-plan.json#work_items[{index - 1}]",
                "work_item_id": item.get("id"),
            }
        )


def _write_plan_artifact(mode: dict[str, Any]) -> Path:
    contract = _contract(mode)
    plan = contract.get("execution_plan") or _load_json_artifact(mode, "implementation-plan.json")
    ui_map = contract.get("ui_code_map") or _load_json_artifact(mode, "ui-code-map.json")
    layout_spec = contract.get("layout_spec") or _load_json_artifact(mode, "ui-layout-spec.json")
    design_tokens = contract.get("design_tokens") or _load_json_artifact(mode, "design-tokens.json")
    interaction_states = contract.get("interaction_state_map") or _load_json_artifact(mode, "interaction-state-map.json")
    visual_acceptance = contract.get("visual_acceptance") or _load_json_artifact(mode, "visual-acceptance.json")
    lines = [
        "# G3 Execution Plan",
        "",
        f"Status: {contract.get('status', 'pending')}",
        "",
        "Generated from `mode.json.event_tree`, `ui-code-map.json`, `ui-layout-spec.json`, `design-tokens.json`, `interaction-state-map.json`, `visual-acceptance.json`, and `implementation-plan.json`.",
        "",
        "## UI Code Map",
        "",
        f"- status: {ui_map.get('status', '')}",
        f"- pencil_authority_file: `{(ui_map.get('generated_from') or {}).get('pencil_authority_file', '')}`",
        "",
        "## UI Implementation Contract",
        "",
        f"- ui-layout-spec.json: {layout_spec.get('status', '')}",
        f"- design-tokens.json: {design_tokens.get('status', '')}",
        f"- interaction-state-map.json: {interaction_states.get('status', '')}",
        f"- visual-acceptance.json: {visual_acceptance.get('status', '')}",
        "",
        "## Work Items",
        "",
    ]
    for item in plan.get("work_items", []):
        lines.extend(
            [
                f"### {item.get('id')} - {item.get('title')}",
                "",
                f"- kind: {item.get('kind')}",
                f"- frame_ids: {', '.join(f'`{frame}`' for frame in item.get('frame_ids', []))}",
                f"- code_targets: {', '.join(f'`{target}`' for target in item.get('code_targets', []))}",
                f"- actions: {', '.join(str(action) for action in item.get('actions', []))}",
                f"- spec_refs: {json.dumps(item.get('spec_refs') or {}, ensure_ascii=False)}",
                "- acceptance_checks:",
            ]
        )
        for check in item.get("acceptance_checks", []):
            lines.append(f"  - {check}")
        lines.append("- verification_commands:")
        for command in item.get("verification_commands", []):
            lines.append(f"  - `{command}`")
        lines.append("")
    lines.extend(
        [
            "## Approval",
            "",
            f"- status: {(mode.get('g3_approval') or {}).get('status', 'pending')}",
        ]
    )
    path = _path_in_run(mode, "04-plan.md")
    write_text(path, "\n".join(lines).rstrip() + "\n")
    return path


def _record_g3_agent_owned_result(mode: dict[str, Any], event_id: str, note: str = "") -> None:
    contract = _contract(mode)
    if event_id == "G3.SCAN_IMPLEMENTATION_SURFACE":
        payload = _extract_json_payload(note, "IMPLEMENTATION_SURFACE_JSON:")
        surface = payload if isinstance(payload, dict) else _default_implementation_surface(mode, note)
        surface.setdefault("status", "ok")
        contract["implementation_surface"] = surface
        return
    if event_id == "G3.MAP_PENCIL_TO_CODE_TARGETS":
        payload = _extract_json_payload(note, "UI_CODE_MAP_JSON:")
        mapping = payload if isinstance(payload, dict) else _default_ui_code_map(mode, note)
        mapping.setdefault("status", "ok" if mapping.get("mappings") else "needs_mapping")
        contract["ui_code_map"] = mapping
        contract["deliverables"]["ui_code_map"] = str(_path_in_run(mode, "ui-code-map.json").resolve())
        _write_ui_code_map(mode, mapping)
        return
    if event_id == "G3.DRAFT_EXECUTION_PLAN":
        if _note_indicates_failure(note):
            plan = contract.get("execution_plan") or _load_json_artifact(mode, "implementation-plan.json")
            if not isinstance(plan, dict) or not plan:
                plan = _write_implementation_plan(mode, contract.get("work_items") or [], note)
            plan["status"] = "needs_repair"
            plan["note"] = note.strip()
            contract["execution_plan"] = plan
            contract["deliverables"]["implementation_plan"] = str(_path_in_run(mode, "implementation-plan.json").resolve())
            write_json(_path_in_run(mode, "implementation-plan.json"), plan)
            return
        payload = _extract_json_payload(note, "IMPLEMENTATION_PLAN_JSON:")
        if isinstance(payload, dict) and isinstance(payload.get("work_items"), list):
            plan = payload
            items = payload["work_items"]
        else:
            existing_items = contract.get("work_items") or []
            items = _default_work_items(mode) if _execution_items_need_regeneration(mode, existing_items) else existing_items
            plan = _write_implementation_plan(mode, items, note)
        contract["work_items"] = items
        contract["execution_plan"] = plan
        contract["deliverables"]["implementation_plan"] = str(_path_in_run(mode, "implementation-plan.json").resolve())
        return
    raise StateError(f"unsupported G3 agent-owned event: {event_id}")


def _assert_ui_code_map_ready(mode: dict[str, Any]) -> None:
    if not _ui_required(mode):
        return
    mapping = _load_json_artifact(mode, "ui-code-map.json")
    if mapping.get("status") != "ok":
        raise StateError(f"ui-code-map status must be ok for UI projects, got {mapping.get('status')!r}")
    if not mapping.get("mappings"):
        raise StateError("ui-code-map must contain mappings for UI projects")
    for item in mapping.get("mappings", []):
        if not item.get("frame_id") or not item.get("code_targets"):
            raise StateError("each ui-code-map mapping must include frame_id and code_targets")


def _assert_ui_implementation_contract_ready(mode: dict[str, Any]) -> None:
    if not _ui_required(mode):
        return
    required = {
        "ui-layout-spec.json": _load_json_artifact(mode, "ui-layout-spec.json"),
        "design-tokens.json": _load_json_artifact(mode, "design-tokens.json"),
        "interaction-state-map.json": _load_json_artifact(mode, "interaction-state-map.json"),
        "visual-acceptance.json": _load_json_artifact(mode, "visual-acceptance.json"),
    }
    for name, artifact in required.items():
        if artifact.get("status") != "ok":
            raise StateError(f"{name} status must be ok for UI projects, got {artifact.get('status')!r}")
    layout = required["ui-layout-spec.json"]
    visual = required["visual-acceptance.json"]
    if not layout.get("top_level_frames"):
        raise StateError("ui-layout-spec.json must include top_level_frames")
    if not visual.get("checks"):
        raise StateError("visual-acceptance.json must include checks")
    mapped = {
        str(item.get("frame_id"))
        for item in _load_json_artifact(mode, "ui-code-map.json").get("mappings", [])
        if item.get("frame_id")
    }
    layout_frames = {str(item.get("frame_id")) for item in layout.get("top_level_frames", []) if item.get("frame_id")}
    visual_frames = {str(item.get("frame_id")) for item in visual.get("checks", []) if item.get("frame_id")}
    if not mapped.issubset(layout_frames):
        raise StateError("ui-layout-spec.json does not cover every mapped UI frame")
    if not mapped.issubset(visual_frames):
        raise StateError("visual-acceptance.json does not cover every mapped UI frame")


def _assert_execution_plan_ready(mode: dict[str, Any]) -> None:
    contract = _contract(mode)
    plan = contract.get("execution_plan") or _load_json_artifact(mode, "implementation-plan.json")
    if isinstance(plan, dict):
        if plan.get("status") != "ok":
            raise StateError(f"implementation-plan status must be ok, got {plan.get('status')!r}")
        if _note_indicates_failure(str(plan.get("note") or "")):
            raise StateError("implementation-plan contains a FAIL note")
    items = contract.get("work_items") or ((plan if isinstance(plan, dict) else {}).get("work_items") or [])
    if not items:
        raise StateError("implementation plan must contain work_items")
    commands = list(dict.fromkeys(command for item in items for command in item.get("verification_commands", []) if isinstance(command, str)))
    if _js_stack_required(mode):
        required_commands = ["npm run typecheck", "npm run build", "npx prisma validate"]
        for command in required_commands:
            if command not in commands:
                raise StateError(f"implementation plan must include `{command}` for the selected stack")
        if "python -m compileall ." in commands:
            raise StateError("python compileall is not a valid verification command for React/Node/Prisma work")
        scaffold_items = [item for item in items if item.get("kind") == "scaffold"]
        if not scaffold_items:
            raise StateError("implementation plan must include a scaffold work item for a from-scratch React/Node project")
        scaffold_targets = set(scaffold_items[0].get("code_targets") or [])
        for target in ["package.json", "vite.config.ts", "src/main.tsx", "src/App.tsx", "server/src/index.ts", "prisma/schema.prisma"]:
            if target not in scaffold_targets:
                raise StateError(f"scaffold work item must include `{target}`")
        data_items = [item for item in items if item.get("kind") in {"data", "data_api", "api"}]
        if _g1_answer(mode, "G1.Q5") and not data_items:
            raise StateError("implementation plan must include a data/API work item")
        if data_items:
            data_targets = set(target for item in data_items for target in item.get("code_targets", []))
            for target in ["prisma/schema.prisma", "server/src/index.ts", "server/src/prisma.ts", "server/src/routes/auth.ts", "server/src/routes/employees.ts"]:
                if target not in data_targets:
                    raise StateError(f"data/API work item must include `{target}`")
    for item in items:
        if not item.get("code_targets"):
            raise StateError(f"work item {item.get('id')} has no code_targets")
        if item.get("kind") == "ui" and not item.get("frame_ids"):
            raise StateError(f"UI work item {item.get('id')} has no frame_ids")
        if item.get("kind") == "ui" and not item.get("spec_refs"):
            raise StateError(f"UI work item {item.get('id')} has no UI implementation spec_refs")
        if item.get("kind") == "ui":
            targets = set(item.get("code_targets") or [])
            frame_ids = {str(frame_id) for frame_id in item.get("frame_ids", [])}
            if "s1_login" in frame_ids and "src/api/auth.ts" not in targets:
                raise StateError("S1 login work item must include src/api/auth.ts")
            if "s2_roster" in frame_ids:
                for target in [
                    "src/components/roster/RosterFilters.tsx",
                    "src/components/roster/RosterStats.tsx",
                    "src/components/roster/EmployeeFormModal.tsx",
                    "src/components/roster/RosterTable.tsx",
                    "src/api/employees.ts",
                ]:
                    if target not in targets:
                        raise StateError(f"S2 roster work item must include `{target}`")
        if not item.get("acceptance_checks") or not item.get("verification_commands"):
            raise StateError(f"work item {item.get('id')} must include acceptance checks and verification commands")


def advance_g3(ws: Workspace, note: str = "", *, trace: bool = True) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g3_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "g3":
        raise StateError("G3 can only advance while stage=g3")
    current = _active_g3_event(mode)
    event_id = str(current.get("id"))
    contract = _contract(mode)

    if event_id == "G3.START":
        if not is_g2_complete(mode):
            raise StateError("G3.START requires G2.COMPLETE")
        current["completed_at"] = utc_now()
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.READ_G1_G2_DELIVERABLES":
        required = ["01-project-definition.md", "02-design.md"]
        missing = [name for name in required if not _path_in_run(mode, name).exists()]
        if missing:
            _block_current(mode, current, f"missing G1/G2 deliverables: {', '.join(missing)}")
            save_mode(ws, mode)
            raise StateError(current["blocked_reason"])
        contract["deliverables"].update(
            {
                "project_definition": str(_path_in_run(mode, "01-project-definition.md").resolve()),
                "design": str(_path_in_run(mode, "02-design.md").resolve()),
            }
        )
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.CHECK_G2_APPROVED":
        approval = mode.get("g2_approval") or {}
        if approval.get("status") != "approved":
            _block_current(mode, current, "G2 approval is required before G3 planning")
            save_mode(ws, mode)
            raise StateError("G2 approval is required before G3 planning")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.LOAD_PENCIL_AUTHORITY":
        if not _ui_required(mode):
            contract["ui"] = {"required": False, "authority": "NO_UI"}
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G3.SCAN_IMPLEMENTATION_SURFACE")
            next_event["status"] = "active"
        else:
            inventory = _load_json_artifact(mode, "frame-inventory.json")
            feature_map = _load_json_artifact(mode, "feature-ui-map.json")
            if int(inventory.get("frame_count", 0) or 0) <= 0:
                _block_current(mode, current, "frame-inventory.json has no frames")
                save_mode(ws, mode)
                raise StateError("frame-inventory.json has no frames")
            if feature_map.get("status") != "ok":
                _block_current(mode, current, f"feature-ui-map status must be ok, got {feature_map.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["ui"] = {
                "required": True,
                "authority": "pencil",
                "pencil_authority_file": feature_map.get("authority_file") or "",
                "frame_count": inventory.get("frame_count", 0),
                "feature_ui_map_status": feature_map.get("status"),
                "frame_ids": [item.get("id") for item in inventory.get("frames", []) if isinstance(item, dict)],
            }
            next_event = _complete_current(mode, event_id)

    elif event_id == "G3.SCAN_IMPLEMENTATION_SURFACE":
        raise StateError("G3.SCAN_IMPLEMENTATION_SURFACE requires architect spawn/result through g3-trace")

    elif event_id == "G3.MAP_PENCIL_TO_CODE_TARGETS":
        raise StateError("G3.MAP_PENCIL_TO_CODE_TARGETS requires designer spawn/result through g3-trace")

    elif event_id == "G3.CHECK_UI_CODE_MAP":
        try:
            _assert_ui_code_map_ready(mode)
        except StateError as exc:
            _block_current(mode, current, str(exc))
            save_mode(ws, mode)
            raise
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.EXTRACT_LAYOUT_SPEC":
        if not _ui_required(mode):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G3.EXTRACT_DESIGN_TOKENS")
            next_event["status"] = "active"
        else:
            spec = _default_layout_spec(mode)
            if spec.get("status") != "ok":
                _block_current(mode, current, f"ui-layout-spec status must be ok, got {spec.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["layout_spec"] = spec
            contract["deliverables"]["layout_spec"] = str(_path_in_run(mode, "ui-layout-spec.json").resolve())
            _write_layout_spec(mode, spec)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G3.EXTRACT_DESIGN_TOKENS":
        if not _ui_required(mode):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G3.MAP_INTERACTION_STATES")
            next_event["status"] = "active"
        else:
            tokens = _default_design_tokens(mode)
            contract["design_tokens"] = tokens
            contract["deliverables"]["design_tokens"] = str(_path_in_run(mode, "design-tokens.json").resolve())
            _write_design_tokens(mode, tokens)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G3.MAP_INTERACTION_STATES":
        if not _ui_required(mode):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G3.WRITE_VISUAL_ACCEPTANCE")
            next_event["status"] = "active"
        else:
            state_map = _default_interaction_state_map(mode)
            if state_map.get("status") != "ok":
                _block_current(mode, current, f"interaction-state-map status must be ok, got {state_map.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["interaction_state_map"] = state_map
            contract["deliverables"]["interaction_state_map"] = str(_path_in_run(mode, "interaction-state-map.json").resolve())
            _write_interaction_state_map(mode, state_map)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G3.WRITE_VISUAL_ACCEPTANCE":
        if not _ui_required(mode):
            current["status"] = "not_applicable"
            next_event = event_by_id(mode, "G3.CHECK_UI_IMPLEMENTATION_CONTRACT")
            next_event["status"] = "active"
        else:
            acceptance = _default_visual_acceptance(mode)
            if acceptance.get("status") != "ok":
                _block_current(mode, current, f"visual-acceptance status must be ok, got {acceptance.get('status')!r}")
                save_mode(ws, mode)
                raise StateError(current["blocked_reason"])
            contract["visual_acceptance"] = acceptance
            contract["deliverables"]["visual_acceptance"] = str(_path_in_run(mode, "visual-acceptance.json").resolve())
            _write_visual_acceptance(mode, acceptance)
            next_event = _complete_current(mode, event_id)

    elif event_id == "G3.CHECK_UI_IMPLEMENTATION_CONTRACT":
        try:
            _assert_ui_implementation_contract_ready(mode)
        except StateError as exc:
            _block_current(mode, current, str(exc))
            save_mode(ws, mode)
            raise
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.MATERIALIZE_WORK_ITEMS":
        items = _default_work_items(mode)
        if not items:
            _block_current(mode, current, "no work items could be materialized")
            save_mode(ws, mode)
            raise StateError("no work items could be materialized")
        contract["work_items"] = items
        plan = _write_implementation_plan(mode, items, "materialized before planner review")
        contract["execution_plan"] = plan
        contract["deliverables"]["implementation_plan"] = str(_path_in_run(mode, "implementation-plan.json").resolve())
        _materialize_work_item_tree(mode, items)
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.DRAFT_EXECUTION_PLAN":
        raise StateError("G3.DRAFT_EXECUTION_PLAN requires planner spawn/result through g3-trace")

    elif event_id == "G3.CHECK_EXECUTION_PLAN":
        try:
            _assert_execution_plan_ready(mode)
        except StateError as exc:
            _block_current(mode, current, str(exc))
            save_mode(ws, mode)
            raise
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.WRITE_PLAN_ARTIFACT":
        contract["status"] = "ready_for_user_approval"
        path = _write_plan_artifact(mode)
        current["answer_ref"] = str(path.resolve())
        contract["deliverables"]["plan_artifact"] = str(path.resolve())
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.READINESS_CHECK":
        _assert_ui_code_map_ready(mode)
        _assert_ui_implementation_contract_ready(mode)
        _assert_execution_plan_ready(mode)
        if not _path_in_run(mode, "04-plan.md").exists():
            raise StateError("04-plan.md is missing")
        next_event = _complete_current(mode, event_id)

    elif event_id == "G3.USER_APPROVAL":
        raise StateError("use g3-approve to record explicit user approval")

    else:
        raise StateError(f"unsupported G3 event: {event_id}")

    mode["status"] = f"{event_id.lower()}_done"
    if trace:
        _trace_g3_transition(mode, event_id, next_event, note)
    save_mode(ws, mode)
    if _path_in_run(mode, "04-plan.md").exists() and event_id not in {"G3.WRITE_PLAN_ARTIFACT"}:
        _write_plan_artifact(mode)
    return {
        "ok": True,
        "event": event_id,
        "status": "done",
        "next_event": next_event.get("id") if next_event else None,
        "plan": str(_path_in_run(mode, "04-plan.md").resolve()),
    }


def g3_status(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    changed = _ensure_g3_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if changed:
        save_mode(ws, mode)
    current = None
    if not is_g3_complete(mode):
        current_event = active_event(mode, "G3") or blocked_event(mode, "G3")
        current = current_event.get("id") if current_event else None
    return {
        "ok": True,
        "active_event": current,
        "complete": is_g3_complete(mode),
        "events": child_events(mode, "G3"),
        "event_tree": mode["event_tree"],
        "contract": _contract(mode),
        "hook_trace": _hook_trace(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "plan": str(_path_in_run(mode, "04-plan.md").resolve()),
    }


def run_g3_hook_trace_until_user_gate(ws: Workspace, before_index: int | None = None) -> dict[str, Any]:
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g3_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "g3":
        raise StateError("G3 hook-trace can only run while stage=g3")
    if before_index is None:
        before_index = len(_hook_trace(mode))
    advanced: list[dict[str, Any]] = []
    while True:
        current = _active_g3_event(mode)
        event_id = str(current.get("id"))
        if event_id in G3_USER_GATE_EVENTS:
            _ensure_g3_user_gate_waiting(mode, event_id)
            mode["status"] = f"{event_id.lower()}_waiting_for_user"
            save_mode(ws, mode)
            if _path_in_run(mode, "04-plan.md").exists():
                _write_plan_artifact(mode)
            return _g3_trace_result(mode, before_index, advanced)
        if event_id in G3_SPAWN_POLICIES:
            _ensure_g3_spawn_required(mode, event_id)
            mode["status"] = f"{event_id.lower()}_waiting_for_spawn"
            save_mode(ws, mode)
            if _path_in_run(mode, "04-plan.md").exists():
                _write_plan_artifact(mode)
            return _g3_trace_result(mode, before_index, advanced)
        result = advance_g3(ws)
        advanced.append({"event": result["event"], "next_event": result.get("next_event")})
        mode = load_mode(ws)
        assert mode is not None
        _ensure_g3_event_tree(mode)
        errors = validate_mode(mode)
        if errors:
            raise StateError("; ".join(errors))


def _trace_g3_agent_result_transition(mode: dict[str, Any], event_id: str, note: str) -> None:
    policy = G3_SPAWN_POLICIES[event_id]
    agent = policy["agent"]
    _complete_agent_call(mode, event_id, agent, note)
    _trace_g3_hook(
        mode,
        f"{event_id}.result_record",
        note.strip(),
        event_id,
        f"record {agent} result",
        {"agent": agent},
    )
    _require_g3_inspector(mode, event_id, f"spawn inspector to check {event_id} before next")


def _complete_g3_after_inspector(mode: dict[str, Any], event_id: str) -> dict[str, Any] | None:
    return _complete_current(mode, event_id)


def _trace_g3_next_after_inspector(mode: dict[str, Any], event_id: str, next_event: dict[str, Any] | None) -> None:
    if next_event is None:
        return
    next_id = str(next_event.get("id") or "")
    _trace_g3_hook(mode, f"{event_id}.next", f"{event_id}=done", event_id, f"advance to {next_id}")
    _trace_g3_hook_once(mode, f"{next_id}.enter", f"{next_id}=active", next_id, "enter active G3 event")


def apply_g3_hook_trace_signal(
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
    _ensure_g3_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    before_index = len(_hook_trace(mode))
    current = _active_g3_event(mode)
    event_id = str(current.get("id"))
    contract = _contract(mode)

    if signal == "spawn-record":
        if event_id not in G3_SPAWN_POLICIES:
            raise StateError(f"active G3 event is {event_id}; cannot record spawn")
        policy = G3_SPAWN_POLICIES[event_id]
        expected_agent = policy["agent"]
        agent_name = agent.strip() or expected_agent
        if agent_name != expected_agent:
            raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")
        _ensure_g3_spawn_required(mode, event_id)
        call_id = agent_id.strip() or f"{agent_name}-local"
        _record_agent_call(mode, event_id, agent_name, call_id, "spawned", policy["scope"])
        _trace_g3_hook(
            mode,
            f"{event_id}.spawn_record",
            f"agent_id={call_id}",
            event_id,
            f"record {agent_name} spawn",
            {"agent": agent_name, "agent_id": call_id, **agent_spawn_contract(agent_name)},
        )
        _trace_g3_hook_once(mode, f"{event_id}.wait_result", "waiting for agent result", event_id, f"wait for {agent_name} result")
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
        return _g3_trace_result(mode, before_index, [])

    if signal == "agent-result":
        if event_id not in G3_SPAWN_POLICIES:
            raise StateError(f"active G3 event is {event_id}; cannot record agent result")
        policy = G3_SPAWN_POLICIES[event_id]
        expected_agent = policy["agent"]
        agent_name = agent.strip() or expected_agent
        if agent_name != expected_agent:
            raise StateError(f"{event_id} requires agent {expected_agent}, got {agent_name}")
        if not _has_agent_call(mode, event_id, expected_agent):
            raise StateError(f"{event_id} requires spawn_record before agent-result")
        _record_g3_agent_owned_result(mode, event_id, note)
        _trace_g3_agent_result_transition(mode, event_id, note)
        mode["status"] = f"{event_id.lower()}_waiting_for_inspector_spawn"
        save_mode(ws, mode)
        if _path_in_run(mode, "04-plan.md").exists():
            _write_plan_artifact(mode)
        return _g3_trace_result(mode, before_index, [])

    if signal == "inspector-spawn-record":
        if _inspector_state(mode).get("pending_event") != event_id:
            raise StateError(f"active G3 event is {event_id}; no inspector check is pending")
        agent_name = agent.strip() or INSPECTOR_AGENT
        if agent_name != INSPECTOR_AGENT:
            raise StateError(f"{event_id} requires agent {INSPECTOR_AGENT}, got {agent_name}")
        _record_g3_inspector_spawn(mode, event_id, agent_id)
        mode["status"] = f"{event_id.lower()}_waiting_for_inspector_result"
        save_mode(ws, mode)
        return _g3_trace_result(mode, before_index, [])

    if signal == "inspector-result":
        if _inspector_state(mode).get("pending_event") != event_id:
            raise StateError(f"active G3 event is {event_id}; no inspector check is pending")
        if not _has_agent_call(mode, event_id, INSPECTOR_AGENT):
            raise StateError(f"{event_id} requires inspector_spawn_record before inspector-result")
        _record_g3_inspector_result(mode, event_id, note)
        if event_id in G3_SPAWN_POLICIES:
            policy = G3_SPAWN_POLICIES[event_id]
            if _latest_agent_result_failed(mode, event_id, policy["agent"]):
                if event_id == "G3.DRAFT_EXECUTION_PLAN":
                    _materialize_execution_plan_for_retry(
                        mode,
                        "repair materialized after inspector-verified planner failure",
                    )
                _trace_g3_hook(
                    mode,
                    f"{event_id}.repair_required",
                    "agent failure verified by inspector",
                    event_id,
                    f"repair {event_id} before retrying {policy['agent']}",
                    {"expected_agent": policy["agent"]},
                )
                if event_id == "G3.DRAFT_EXECUTION_PLAN":
                    _trace_g3_hook(
                        mode,
                        f"{event_id}.repair_materialized",
                        "implementation-plan.json regenerated for retry",
                        event_id,
                        "materialize repaired execution plan before retry",
                        {"artifact": "implementation-plan.json"},
                    )
                _set_orchestrator(
                    mode,
                    event_id,
                    spawn_decision="required",
                    spawn_status="pending",
                    expected_agent=policy["agent"],
                    instruction=f"repair {event_id}; then spawn {policy['agent']} again",
                )
                _inspector_state(mode).pop("pending_event", None)
                mode["status"] = f"{event_id.lower()}_waiting_for_repair"
                save_mode(ws, mode)
                return _g3_trace_result(mode, before_index, [])
            next_event = _complete_g3_after_inspector(mode, event_id)
            _trace_g3_next_after_inspector(mode, event_id, next_event)
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
            return run_g3_hook_trace_until_user_gate(ws, before_index)
        if event_id == "G3.USER_APPROVAL":
            approval_note = str(mode.pop("pending_g3_approval_note", "") or note).strip()
            save_mode(ws, mode)
            approve_g3(ws, note=approval_note)
            mode = load_mode(ws)
            assert mode is not None
            _inspector_state(mode).pop("pending_event", None)
            save_mode(ws, mode)
            return _g3_trace_result(mode, before_index, [])
        raise StateError(f"unsupported G3 inspector event: {event_id}")

    if signal == "approve-g3":
        if event_id != "G3.USER_APPROVAL":
            raise StateError(f"active G3 event is {event_id}; cannot record approve-g3")
        if _event(mode, "G3.READINESS_CHECK").get("status") != "done":
            raise StateError("G3.READINESS_CHECK must be done before user approval")
        _ensure_g3_user_gate_waiting(mode, event_id)
        _trace_g3_hook(
            mode,
            "G3.USER_APPROVAL.record",
            note.strip() or "user approved G3",
            "G3.USER_APPROVAL",
            "record explicit G3 approval",
            {"approved_by": "user"},
        )
        mode["pending_g3_approval_note"] = note.strip()
        _require_g3_inspector(mode, event_id, "spawn inspector to check G3 approval before phase transition")
        save_mode(ws, mode)
        return _g3_trace_result(mode, before_index, [])

    raise StateError("signal must be one of: spawn-record, agent-result, inspector-spawn-record, inspector-result, approve-g3")


def approve_g3(ws: Workspace, note: str = "", approved_by: str = "user") -> dict[str, Any]:
    if approved_by != "user":
        raise StateError("G3 approval must be approved_by='user'")
    mode = load_mode(ws)
    if not isinstance(mode, dict):
        raise StateError("mode.json is missing or is not an object")
    _ensure_g3_event_tree(mode)
    errors = validate_mode(mode)
    if errors:
        raise StateError("; ".join(errors))
    if mode.get("stage") != "g3":
        raise StateError("G3 approval can only be recorded while stage=g3")
    current = _active_g3_event(mode)
    if current.get("id") != "G3.USER_APPROVAL":
        raise StateError(f"active G3 event is {current.get('id')}; cannot approve G3")
    now = utc_now()
    approval = mode.setdefault("g3_approval", {})
    approval["status"] = "approved"
    approval["approved_by"] = approved_by
    approval["approved_at"] = now
    approval["note"] = note.strip()
    current["answer_ref"] = "mode.json:g3_approval"
    try:
        next_event = mark_active_event_terminal(mode, "G3.USER_APPROVAL", "done")
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    _trace_g3_hook(mode, "G3.USER_APPROVAL.next", "G3.USER_APPROVAL=done", "G3.USER_APPROVAL", "advance to G3.COMPLETE")
    if next_event is None or next_event.get("id") != "G3.COMPLETE":
        raise StateError("G3.USER_APPROVAL did not advance to G3.COMPLETE")
    _trace_g3_hook_once(mode, "G3.COMPLETE.enter", "G3.COMPLETE=active", "G3.COMPLETE", "enter active G3 event")
    next_event["status"] = "done"
    next_event["completed_at"] = now
    _trace_g3_hook(mode, "G3.COMPLETE.record", "runtime recorded event result", "G3.COMPLETE", "record G3 completion")
    transition_to_phase(mode, "G4")
    _trace_g3_hook(mode, "G3.COMPLETE.next", "G3.COMPLETE=done", "G3.COMPLETE", "advance to G4")
    next_g4 = active_event(mode, "G4")
    next_g4_id = str(next_g4.get("id") if next_g4 else "G4")
    _clear_orchestrator(mode, next_g4_id, "G3 complete; enter G4 with no pending G3 agent")
    _set_inspector(mode, next_g4_id, status="not_required", checkpoint_required=False)
    mode["status"] = "execute_ready"
    save_mode(ws, mode)
    return {
        "ok": True,
        "event": "G3.COMPLETE",
        "next_global_event": "G4",
        "next_event": active_event(mode, "G4").get("id") if active_event(mode, "G4") else None,
        "plan": str(_path_in_run(mode, "04-plan.md").resolve()),
    }


def _g3_trace_result(mode: dict[str, Any], before_index: int, advanced: list[dict[str, Any]]) -> dict[str, Any]:
    current_event = None
    if not is_g3_complete(mode):
        current = active_event(mode, "G3") or blocked_event(mode, "G3")
        current_event = current.get("id") if current else None
    trace = _hook_trace(mode)
    return {
        "ok": True,
        "active_event": current_event,
        "complete": is_g3_complete(mode),
        "advanced": advanced,
        "trace": trace[before_index:],
        "trace_hooks": [item.get("hook") for item in trace[before_index:]],
        "contract": _contract(mode),
        "orchestrator": _orchestrator_state(mode),
        "inspector": _inspector_state(mode),
        "plan": str(_path_in_run(mode, "04-plan.md").resolve()),
    }
