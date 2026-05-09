from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .event_tree import active_event, blocked_event
from .state import load_mode, save_mode, validate_mode
from .tdd import observe_test_result, write_guidance_message
from .workspace import SUPER_DIR_NAME, Workspace, utc_now


WRITE_TOOLS = {"apply_patch", "shell_command"}
PENCIL_WRITE_TOOLS = {
    "batch-design",
    "batch_design",
    "mcp__pencil__batch_design",
    "open-document",
    "open_document",
    "mcp__pencil__open_document",
    "set-variables",
    "set_variables",
    "mcp__pencil__set_variables",
    "replace-all-matching-properties",
    "replace_all_matching_properties",
    "mcp__pencil__replace_all_matching_properties",
}
WRITE_COMMAND_RE = re.compile(
    r"\b(Set-Content|Out-File|Remove-Item|Move-Item|Copy-Item|New-Item|del|erase|rm|mv|cp)\b",
    re.IGNORECASE,
)
RUN_INVOCATION_RE = re.compile(r"(?:(?:/|\$)superteam:go|\$go)\b", re.IGNORECASE)
EVENT_ALIASES = {
    "sessionStart": "SessionStart",
    "userPromptSubmit": "UserPromptSubmit",
    "preToolUse": "PreToolUse",
    "postToolUse": "PostToolUse",
    "permissionRequest": "PermissionRequest",
    "stop": "Stop",
}


def read_hook_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def _workspace_from_payload(payload: dict[str, Any]) -> Workspace | None:
    candidates = [
        payload.get("cwd"),
        payload.get("project_root"),
        os.environ.get("CODEX_WORKSPACE"),
        os.getcwd(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).resolve()
        if (path / SUPER_DIR_NAME).exists():
            return Workspace(path)
        for parent in path.parents:
            if (parent / SUPER_DIR_NAME).exists():
                return Workspace(parent)
    return None


def _is_write_payload(payload: dict[str, Any]) -> bool:
    tool = str(payload.get("tool") or payload.get("tool_name") or payload.get("name") or "")
    if tool in WRITE_TOOLS:
        return True
    if tool.lower() in PENCIL_WRITE_TOOLS:
        return True
    text = json.dumps(payload, ensure_ascii=False)
    return bool(WRITE_COMMAND_RE.search(text))


def _payload_mentions_superteam_state(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False)
    return SUPER_DIR_NAME in text


def _payload_mentions_pencil_design(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False).lower()
    tool = str(payload.get("tool") or payload.get("tool_name") or payload.get("name") or "").lower()
    return (
        tool in PENCIL_WRITE_TOOLS
        or
        ".pen" in text
        or "\\pencil\\" in text
        or "/pencil/" in text
        or "pencil" in text and "asset" in text
    )


def _payload_invokes_superteam_run(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False)
    return bool(RUN_INVOCATION_RE.search(text))


def _active_leaf_id(mode: dict[str, Any]) -> str:
    current = active_event(mode) or blocked_event(mode)
    return str(current.get("id") or "") if current else ""


def _append_hook_audit(ws: Workspace, mode: dict[str, Any], event: str, payload: dict[str, Any], code: int, message: str) -> None:
    try:
        path = ws.state_dir / "hook-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": utc_now(),
            "event": event,
            "stage": mode.get("stage"),
            "active_leaf_event": _active_leaf_id(mode),
            "tool": payload.get("tool") or payload.get("tool_name") or payload.get("name"),
            "decision": "block" if code else "allow",
            "message": message,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _append_mode_hook_trace(
    ws: Workspace,
    mode: dict[str, Any],
    event: str,
    payload: dict[str, Any],
    code: int,
    message: str,
) -> None:
    try:
        trace = mode.setdefault("hook_trace", [])
        if not isinstance(trace, list):
            trace = []
            mode["hook_trace"] = trace
        trace.append(
            {
                "ts": utc_now(),
                "hook": event,
                "trigger": "SuperTeam internal hook-trace",
                "stage": mode.get("stage"),
                "active_leaf_event": _active_leaf_id(mode),
                "tool": payload.get("tool") or payload.get("tool_name") or payload.get("name"),
                "decision": "block" if code else "allow",
                "message": message,
            }
        )
        save_mode(ws, mode)
    except OSError:
        pass


def handle_event(event: str, payload: dict[str, Any]) -> tuple[int, str]:
    event = EVENT_ALIASES.get(event, event)
    ws = _workspace_from_payload(payload)
    if ws is None:
        return 0, ""
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors or not mode or mode.get("project_lifecycle") != "running":
        return 0, ""

    stage = mode.get("stage")
    guard = mode.get("guard", {})
    active_leaf = _active_leaf_id(mode)

    def finish(code: int, message: str) -> tuple[int, str]:
        _append_hook_audit(ws, mode, event, payload, code, message)
        _append_mode_hook_trace(ws, mode, event, payload, code, message)
        return code, message

    if event == "UserPromptSubmit" and guard.get("block_nested_superteam_run", True):
        if _payload_invokes_superteam_run(payload):
            return finish(
                2,
                "SuperTeam Codex blocked a nested run. The active event_tree already owns this project; treat the request as a child task of the current global stage.",
            )

    if event == "PreToolUse" and _is_write_payload(payload):
        if stage in {"g1", "g2", "g3"}:
            if _payload_mentions_superteam_state(payload):
                return finish(0, "")
            if (
                stage == "g2"
                and active_leaf in {"G2.CREATE_PENCIL_PROJECT", "G2.OPEN_PENCIL", "G2.DESIGN_PENCIL_STEPS"}
                and _payload_mentions_pencil_design(payload)
            ):
                return finish(0, "")
            return finish(
                2,
                f"SuperTeam Codex blocked a write before execute. Complete the active event_tree gate first; active_leaf_event={active_leaf}.",
            )
        if stage == "execute":
            if _payload_mentions_superteam_state(payload):
                return finish(0, "")
            message = write_guidance_message(mode, payload)
            if message:
                return finish(0, message)

    if event == "PostToolUse" and stage == "execute":
        observed = observe_test_result(mode, payload)
        if observed:
            trace = mode.setdefault("hook_trace", [])
            if not isinstance(trace, list):
                trace = []
                mode["hook_trace"] = trace
            trace.append(
                {
                    "ts": utc_now(),
                    "hook": "G4.TDD.post_tool_observer",
                    "trigger": "native Codex PostToolUse",
                    "stage": stage,
                    "active_leaf_event": active_leaf,
                    "tool": payload.get("tool") or payload.get("tool_name") or payload.get("name"),
                    "decision": "record",
                    "tdd": observed,
                }
            )

    if event == "Stop" and guard.get("strict_stop_guard", True):
        if stage in {"execute", "review", "verify"} and mode.get("status") not in {"pass", "complete", "paused"}:
            return finish(
                2,
                "SuperTeam Codex run is still active. Use pause/end/finish or complete the current execution-class stage.",
            )

    return finish(0, "")
