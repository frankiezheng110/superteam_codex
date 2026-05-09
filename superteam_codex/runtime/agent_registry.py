from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path


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


def agent_spawn_contract(agent: str) -> dict[str, object]:
    role = require_superteam_agent(agent)
    path = agent_definition_path(role)
    return {
        "agent_rules_required": True,
        "agent_definition_path": str(path),
        "rules_sha256": file_sha256(path),
        "spawn_prompt_contract": f"Before acting as {role}, load and follow this original SuperTeam agent definition: {path}. OR must not impersonate {role}.",
    }
