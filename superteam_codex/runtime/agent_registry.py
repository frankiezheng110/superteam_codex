from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


SUPERTEAM_AGENT_ROLES = {
    "analyst",
    "architect",
    "debugger",
    "designer",
    "doc-polisher",
    "executor",
    "inspector",
    "planner",
    "prd-writer",
    "release-curator",
    "researcher",
    "reviewer",
    "simplifier",
    "test-engineer",
    "verifier",
    "writer",
}

DEPRECATED_SUPERTEAM_AGENT_ROLES = {
    "orchestrator",
}

SUPERTEAM_AGENT_ROOT_CANDIDATES = [
    Path(os.environ["SUPERTEAM_AGENT_ROOT"]).expanduser() if os.environ.get("SUPERTEAM_AGENT_ROOT") else None,
    Path.home() / ".codex" / "plugins" / "cache" / "frankie-local" / "superteam" / "5.0.0" / "agents",
    Path.home() / "plugins" / "superteam" / "agents",
    Path("D:/codex/superteam/agents"),
]

AGENT_ROSTER_SCHEMA = "superteam_codex.agent_roster.v1"


def require_superteam_agent(agent: str, *, context: str = "agent") -> str:
    name = agent.strip()
    if name in DEPRECATED_SUPERTEAM_AGENT_ROLES:
        raise ValueError(f"{context} uses deprecated SuperTeam agent role: {name}")
    if name not in SUPERTEAM_AGENT_ROLES:
        raise ValueError(f"{context} uses unknown SuperTeam agent role: {name}")
    return name


def validate_spawn_policies(policies: Mapping[str, Mapping[str, str]], *, context: str) -> None:
    for event_id, policy in policies.items():
        require_superteam_agent(str(policy.get("agent") or ""), context=f"{context}.{event_id}")


def agent_definition_path(agent: str) -> Path:
    role = require_superteam_agent(agent)
    filename = f"{role}.md"
    for root in SUPERTEAM_AGENT_ROOT_CANDIDATES:
        if root is None:
            continue
        path = root / filename
        if path.exists():
            return path.resolve()
    roots = [str(root) for root in SUPERTEAM_AGENT_ROOT_CANDIDATES if root is not None]
    raise FileNotFoundError(f"SuperTeam agent definition not found for {role}; searched: {roots}")


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_agent_slot_id(agent: str) -> str:
    role = require_superteam_agent(agent)
    return f"superteam-{role}"


def _agent_slot_placeholder_ids(role: str) -> set[str]:
    return {stable_agent_slot_id(role), f"{role}-local"}


def agent_definition_contract(agent: str) -> dict[str, object]:
    role = require_superteam_agent(agent)
    path = agent_definition_path(role)
    return {
        "role": role,
        "agent_rules_required": True,
        "agent_definition_path": str(path),
        "rules_sha256": file_sha256(path),
        "agent_definition_binding": f"mode.json:agent_roster.roles.{role}",
        "codex_display_name_is_identity": False,
        "agent_call_policy": "initialize_once_then_send_input",
    }


def build_agent_roster(roles: Iterable[str] | None = None) -> dict[str, Any]:
    selected_roles = sorted(roles if roles is not None else SUPERTEAM_AGENT_ROLES)
    role_contracts = {
        require_superteam_agent(role): agent_definition_contract(role)
        for role in selected_roles
    }
    return {
        "schema": AGENT_ROSTER_SCHEMA,
        "created_at": utc_now(),
        "identity_rule": "SuperTeam role identity is role + agent_definition_path + rules_sha256, not the Codex UI display name.",
        "call_rule": "Use spawn_agent only to initialize a missing role slot; after mode.json.agent_slots.<role>.agent_id exists, use send_input.",
        "roles": role_contracts,
    }


def ensure_agent_roster(mode: dict[str, Any]) -> dict[str, Any]:
    roster = mode.get("agent_roster")
    if not isinstance(roster, dict) or not isinstance(roster.get("roles"), dict):
        roster = build_agent_roster()
        mode["agent_roster"] = roster
        return roster

    roles = roster.setdefault("roles", {})
    if not isinstance(roles, dict):
        roster = build_agent_roster()
        mode["agent_roster"] = roster
        return roster

    roster.setdefault("schema", AGENT_ROSTER_SCHEMA)
    roster.setdefault(
        "identity_rule",
        "SuperTeam role identity is role + agent_definition_path + rules_sha256, not the Codex UI display name.",
    )
    roster.setdefault(
        "call_rule",
        "Use spawn_agent only to initialize a missing role slot; after mode.json.agent_slots.<role>.agent_id exists, use send_input.",
    )
    for role in sorted(SUPERTEAM_AGENT_ROLES):
        if not isinstance(roles.get(role), dict):
            roles[role] = agent_definition_contract(role)
    return roster


def agent_roster_contract(mode: dict[str, Any], agent: str) -> dict[str, object]:
    role = require_superteam_agent(agent)
    roster = ensure_agent_roster(mode)
    roles = roster.get("roles")
    if not isinstance(roles, dict) or not isinstance(roles.get(role), dict):
        raise ValueError(f"mode.json.agent_roster.roles.{role} is missing")
    return dict(roles[role])


def validate_agent_roster(mode: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    roster = mode.get("agent_roster")
    if not isinstance(roster, dict):
        return ["agent_roster must be an object"]
    if roster.get("schema") != AGENT_ROSTER_SCHEMA:
        errors.append(f"agent_roster has unexpected schema: {roster.get('schema')!r}")
    roles = roster.get("roles")
    if not isinstance(roles, dict):
        return errors + ["agent_roster.roles must be an object"]

    for role in sorted(SUPERTEAM_AGENT_ROLES):
        entry = roles.get(role)
        if not isinstance(entry, dict):
            errors.append(f"agent_roster.roles.{role} is missing")
            continue
        expected = agent_definition_contract(role)
        for key in ["agent_definition_path", "rules_sha256"]:
            if entry.get(key) != expected[key]:
                errors.append(f"agent_roster.roles.{role}.{key} does not match the fixed agent definition")

    slots = mode.get("agent_slots")
    if isinstance(slots, dict):
        for role, slot in slots.items():
            if not isinstance(slot, dict) or role not in SUPERTEAM_AGENT_ROLES:
                continue
            roster_entry = roles.get(role)
            if not isinstance(roster_entry, dict):
                continue
            for key in ["agent_definition_path", "rules_sha256"]:
                if slot.get(key) and slot.get(key) != roster_entry.get(key):
                    errors.append(f"agent_slots.{role}.{key} does not match agent_roster")

    calls = (mode.get("orchestrator") or {}).get("agent_calls")
    if isinstance(calls, list):
        for call in calls:
            if not isinstance(call, dict):
                continue
            role = str(call.get("role") or "").strip()
            if role not in SUPERTEAM_AGENT_ROLES:
                continue
            roster_entry = roles.get(role)
            if not isinstance(roster_entry, dict):
                continue
            for key in ["agent_definition_path", "rules_sha256"]:
                if call.get(key) and call.get(key) != roster_entry.get(key):
                    errors.append(f"agent call {call.get('event')} for {role} has {key} outside agent_roster")
    return errors


def agent_slot_payload(agent: str) -> dict[str, object]:
    role = require_superteam_agent(agent)
    slot_id = stable_agent_slot_id(role)
    return {
        "agent_slot_role": role,
        "stable_agent_slot_id": slot_id,
        "agent_reuse_required": True,
        "agent_reuse_instruction": (
            f"Call {role} through mode.json.agent_roster.roles.{role}. "
            f"If mode.json.agent_slots.{role}.agent_id exists, use send_input to that id. "
            f"Use spawn_agent only to initialize a missing {role} slot, then bind it to {slot_id}. "
            "Do not create event-specific agent names or treat Codex display names as identity."
        ),
    }


def agent_reuse_hook_instruction(agent: str, instruction: str) -> str:
    role = require_superteam_agent(agent)
    return (
        f"Call {role} through fixed agent definition mode.json.agent_roster.roles.{role}. "
        f"Before any spawn_agent, check mode.json.agent_slots.{role}.agent_id. "
        f"If it exists, use send_input and record the same agent_id. "
        f"Use spawn_agent only to initialize a missing {role} slot. {instruction}"
    )


def agent_spawn_contract(agent: str) -> dict[str, object]:
    role = require_superteam_agent(agent)
    definition = agent_definition_contract(role)
    return {
        **definition,
        "agent_roster_required": True,
        "spawn_prompt_contract": (
            f"Before acting as {role}, load and follow this original SuperTeam agent definition: "
            f"{definition['agent_definition_path']}. OR must not impersonate {role}. Codex display names are ignored."
        ),
        **agent_slot_payload(role),
    }


def agent_slots(mode: dict[str, Any]) -> dict[str, Any]:
    slots = mode.setdefault("agent_slots", {})
    if not isinstance(slots, dict):
        slots = {}
        mode["agent_slots"] = slots
    return slots


def register_agent_call(
    mode: dict[str, Any],
    event_id: str,
    agent: str,
    agent_id: str,
    status: str,
    scope: str,
) -> dict[str, Any]:
    role = require_superteam_agent(agent)
    requested_id = agent_id.strip()
    placeholder_ids = _agent_slot_placeholder_ids(role)
    roster_contract = agent_roster_contract(mode, role)
    slots = agent_slots(mode)
    slot = slots.get(role)
    reused = False
    if isinstance(slot, dict) and str(slot.get("agent_id") or "").strip():
        call_id = str(slot["agent_id"]).strip()
        if requested_id and requested_id != call_id and requested_id not in placeholder_ids:
            raise ValueError(
                f"{role} already has reusable agent slot {call_id}; reuse it with send_input instead of spawning {requested_id}"
            )
        reused = True
    else:
        call_id = requested_id if requested_id and requested_id not in placeholder_ids else stable_agent_slot_id(role)
        slot = {
            "role": role,
            "agent_id": call_id,
            "status": "active",
            "created_at": utc_now(),
            "created_by_event": event_id,
            **agent_spawn_contract(role),
            **roster_contract,
        }
        slots[role] = slot

    assert isinstance(slot, dict)
    slot["last_event"] = event_id
    slot["last_scope"] = scope
    slot["last_used_at"] = utc_now()
    slot["reuse_count"] = int(slot.get("reuse_count") or 0) + (1 if reused else 0)

    calls = mode.setdefault("orchestrator", {}).setdefault("agent_calls", [])
    if not isinstance(calls, list):
        calls = []
        mode.setdefault("orchestrator", {})["agent_calls"] = calls
    call = {
        "ts": utc_now(),
        "event": event_id,
        "role": role,
        "agent_id": call_id,
        "scope": scope,
        "status": status,
        "agent_slot_role": role,
        "agent_slot_id": call_id,
        "agent_slot_reused": reused,
        "agent_slot_action": "reuse_existing_agent" if reused else "spawn_new_agent_slot",
        "agent_runtime_action": "send_input" if reused else "spawn_agent_initial_slot",
        "agent_identity_source": f"mode.json:agent_roster.roles.{role}",
        "codex_display_name_ignored": True,
        **agent_spawn_contract(role),
        **roster_contract,
    }
    calls.append(call)
    return call
