from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .state import StateError
from .workspace import utc_now


PENDING = "PENDING"
RED_LOCKED = "RED_LOCKED"
GREEN_CONFIRMED = "GREEN_CONFIRMED"
BLOCKED = "BLOCKED"
DEFERRED = "DEFERRED"
TERMINAL_STATES = {GREEN_CONFIRMED, BLOCKED, DEFERRED}
TDD_SIGNALS = {"tdd-red", "tdd-green", "tdd-next", "tdd-blocked", "tdd-deferred"}

PROD_CODE_EXT = re.compile(
    r"\.(py|js|jsx|ts|tsx|rs|go|java|rb|cs|php|swift|kt|kts|cpp|c|h|hpp|vue|svelte|css|scss|prisma)$",
    re.IGNORECASE,
)
TEST_PATH_HINT = re.compile(
    r"(?i)(^|[/\\])(tests?|__tests?__|spec|specs|test)[/\\]|"
    r"\.(test|spec)\.[a-zA-Z0-9]+$|_test\.[a-zA-Z0-9]+$|_spec\.[a-zA-Z0-9]+$"
)
DOC_EXT = re.compile(r"\.(md|markdown|txt|rst)$", re.IGNORECASE)
PROD_BASENAMES = {
    ".env",
    "dockerfile",
    "makefile",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    "vite.config.js",
    "vite.config.ts",
}
PATH_TOKEN_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[A-Za-z0-9_.\-/\\]+(?:"
    r"\.py|\.js|\.jsx|\.ts|\.tsx|\.rs|\.go|\.java|\.rb|\.cs|\.php|\.swift|\.kt|\.kts|"
    r"\.cpp|\.c|\.h|\.hpp|\.vue|\.svelte|\.css|\.scss|\.prisma|package\.json|"
    r"package-lock\.json|pnpm-lock\.yaml|yarn\.lock|tsconfig\.json|\.env"
    r"))",
    re.IGNORECASE,
)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File:\s*(?P<path>.+?)\s*$", re.MULTILINE)
TEST_COMMAND_RE = re.compile(
    r"(?i)\b(pytest|unittest|vitest|jest|mocha|go test|cargo test|dotnet test|mvn test|gradle test)\b|"
    r"\b(npm|pnpm|yarn)\s+(?:run\s+)?(?:test|test:[\w:-]+)\b"
)


def _norm_path(path: str) -> str:
    return path.strip().strip("`\"'").replace("\\", "/")


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH_HINT.search(_norm_path(path)))


def is_production_code_path(path: str) -> bool:
    clean = _norm_path(path)
    if not clean:
        return False
    lower = clean.lower()
    if "/.superteam_codex/" in f"/{lower}/" or lower.startswith(".superteam_codex/"):
        return False
    if is_test_path(clean):
        return False
    name = Path(clean).name.lower()
    if name in PROD_BASENAMES or name.startswith(".env"):
        return True
    if DOC_EXT.search(clean):
        return False
    return bool(PROD_CODE_EXT.search(clean))


def _item_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("id") or f"WI-{index:03d}")


def code_changing_work_items(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    items = plan.get("work_items")
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            continue
        targets = [str(item) for item in raw.get("code_targets") or [] if str(item).strip()]
        prod_targets = [target for target in targets if is_production_code_path(target)]
        if not prod_targets:
            continue
        item = dict(raw)
        item["id"] = _item_id(item, index)
        item["production_code_targets"] = prod_targets
        result.append(item)
    return result


def ensure_tdd_state(mode: dict[str, Any], plan: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = mode.setdefault("g4_contract", {})
    if plan is None:
        plan = contract.get("execution_plan") if isinstance(contract.get("execution_plan"), dict) else None
    tdd = contract.setdefault("tdd", {})
    if not isinstance(tdd, dict):
        tdd = {}
        contract["tdd"] = tdd

    work_items = code_changing_work_items(plan)
    old_items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    new_items: dict[str, Any] = {}
    order: list[str] = []
    for raw in work_items:
        item_id = str(raw["id"])
        order.append(item_id)
        old = old_items.get(item_id, {}) if isinstance(old_items, dict) else {}
        new_items[item_id] = {
            "id": item_id,
            "kind": str(raw.get("kind") or ""),
            "title": str(raw.get("title") or raw.get("kind") or item_id),
            "state": str(old.get("state") or PENDING),
            "red_evidence": old.get("red_evidence"),
            "green_evidence": old.get("green_evidence"),
            "blocked_evidence": old.get("blocked_evidence"),
            "deferred_evidence": old.get("deferred_evidence"),
            "green_attempts": int(old.get("green_attempts") or 0),
            "frame_ids": list(raw.get("frame_ids") or []),
            "spec_refs": raw.get("spec_refs") if isinstance(raw.get("spec_refs"), dict) else {},
            "acceptance_checks": list(raw.get("acceptance_checks") or []),
            "ui_guidance": old.get("ui_guidance"),
            "code_targets": list(raw.get("code_targets") or []),
            "production_code_targets": list(raw.get("production_code_targets") or []),
            "verification_commands": list(raw.get("verification_commands") or []),
        }

    tdd["required"] = bool(new_items)
    tdd["work_item_order"] = order
    tdd["items"] = new_items
    active_id = str(tdd.get("active_work_item_id") or "")
    if active_id and active_id not in new_items:
        active_id = ""
    if not active_id and new_items:
        active_id = next((item_id for item_id in order if new_items[item_id].get("state") not in TERMINAL_STATES), "")
    tdd["active_work_item_id"] = active_id or None
    _refresh_tdd_status(tdd)
    return tdd


def _refresh_tdd_status(tdd: dict[str, Any]) -> None:
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    order = tdd.get("work_item_order") if isinstance(tdd.get("work_item_order"), list) else []
    if not tdd.get("required"):
        tdd["status"] = "not_required"
        tdd["active_work_item_id"] = None
        return
    if order and all(items.get(item_id, {}).get("state") in TERMINAL_STATES for item_id in order):
        if tdd.get("active_work_item_id") not in items:
            tdd["active_work_item_id"] = None
        tdd["status"] = "complete"
        return
    tdd["status"] = "active"


def _active_item(tdd: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    active_id = tdd.get("active_work_item_id")
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    if not active_id or active_id not in items:
        raise StateError("G4 TDD has no active work item; either all items are complete or TDD was not initialized")
    return str(active_id), items[str(active_id)]


def _assert_active_item(tdd: dict[str, Any], work_item_id: str = "") -> tuple[str, dict[str, Any]]:
    active_id, item = _active_item(tdd)
    if work_item_id and work_item_id != active_id:
        raise StateError(f"G4 TDD active work item is {active_id}; cannot record evidence for {work_item_id}")
    return active_id, item


def _evidence(
    *,
    command: str,
    note: str,
    passed: int | None,
    failed: int | None,
    test_file: str,
    source: str,
) -> dict[str, Any]:
    excerpt = note.strip()
    digest_source = "\n".join([command.strip(), test_file.strip(), excerpt])
    return {
        "recorded_at": utc_now(),
        "command": command.strip(),
        "test_file": test_file.strip(),
        "passed": passed,
        "failed": failed,
        "output_sha256": hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16],
        "output_excerpt": excerpt[:1000],
        "source": source,
    }


def apply_tdd_signal(
    mode: dict[str, Any],
    signal: str,
    note: str = "",
    *,
    work_item_id: str = "",
    command: str = "",
    test_file: str = "",
    passed: int | None = None,
    failed: int | None = None,
    source: str = "hook-trace",
) -> dict[str, Any]:
    if signal not in TDD_SIGNALS:
        raise StateError(f"unsupported TDD signal: {signal}")
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        raise StateError("G4 TDD is not required because implementation-plan.json has no code-changing work items")

    if signal == "tdd-red":
        active_id, item = _assert_active_item(tdd, work_item_id)
        if item.get("state") != PENDING:
            raise StateError(f"{active_id} must be {PENDING} before tdd-red; current state is {item.get('state')}")
        if failed is None or failed <= 0:
            raise StateError("tdd-red requires --failed with a value greater than 0")
        item["state"] = RED_LOCKED
        item["red_evidence"] = _evidence(
            command=command,
            note=note,
            passed=passed,
            failed=failed,
            test_file=test_file,
            source=source,
        )
        item["green_attempts"] = 0
        _refresh_tdd_status(tdd)
        return {"work_item_id": active_id, "state": RED_LOCKED, "status": tdd.get("status")}

    if signal == "tdd-green":
        active_id, item = _assert_active_item(tdd, work_item_id)
        if item.get("state") != RED_LOCKED:
            raise StateError(f"{active_id} must be {RED_LOCKED} before tdd-green; current state is {item.get('state')}")
        if failed is None or failed != 0:
            raise StateError("tdd-green requires --failed 0")
        if passed is None or passed <= 0:
            raise StateError("tdd-green requires --passed with a value greater than 0")
        item["state"] = GREEN_CONFIRMED
        item["green_evidence"] = _evidence(
            command=command,
            note=note,
            passed=passed,
            failed=failed,
            test_file=test_file,
            source=source,
        )
        _refresh_tdd_status(tdd)
        return {"work_item_id": active_id, "state": GREEN_CONFIRMED, "status": tdd.get("status")}

    if signal == "tdd-blocked":
        active_id, item = _assert_active_item(tdd, work_item_id)
        if not note.strip():
            raise StateError("tdd-blocked requires an escalation note")
        item["state"] = BLOCKED
        item["blocked_evidence"] = {"recorded_at": utc_now(), "note": note.strip(), "source": source}
        _refresh_tdd_status(tdd)
        return {"work_item_id": active_id, "state": BLOCKED, "status": tdd.get("status")}

    if signal == "tdd-deferred":
        active_id, item = _assert_active_item(tdd, work_item_id)
        if not note.strip():
            raise StateError("tdd-deferred requires an OR decision note")
        item["state"] = DEFERRED
        item["deferred_evidence"] = {"recorded_at": utc_now(), "note": note.strip(), "source": source}
        _refresh_tdd_status(tdd)
        return {"work_item_id": active_id, "state": DEFERRED, "status": tdd.get("status")}

    active_id, item = _active_item(tdd)
    if item.get("state") not in TERMINAL_STATES:
        raise StateError(f"{active_id} is {item.get('state')}; finish RED/GREEN or record BLOCKED/DEFERRED before tdd-next")
    order = list(tdd.get("work_item_order") or [])
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    start = order.index(active_id) + 1 if active_id in order else 0
    next_id = next((item_id for item_id in order[start:] if items.get(item_id, {}).get("state") not in TERMINAL_STATES), None)
    tdd["active_work_item_id"] = next_id
    _refresh_tdd_status(tdd)
    return {"work_item_id": next_id, "previous_work_item_id": active_id, "state": items.get(next_id, {}).get("state") if next_id else None, "status": tdd.get("status")}


def tdd_completion_errors(mode: dict[str, Any]) -> list[str]:
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        return []
    errors: list[str] = []
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    for item_id in tdd.get("work_item_order") or []:
        item = items.get(item_id, {})
        state = item.get("state")
        if state == GREEN_CONFIRMED:
            if not item.get("red_evidence"):
                errors.append(f"{item_id} is GREEN_CONFIRMED but missing RED evidence")
            if not item.get("green_evidence"):
                errors.append(f"{item_id} is GREEN_CONFIRMED but missing GREEN evidence")
        elif state == DEFERRED:
            if not item.get("deferred_evidence"):
                errors.append(f"{item_id} is DEFERRED but missing OR decision evidence")
        elif state == BLOCKED:
            errors.append(f"{item_id} is BLOCKED; G4 cannot advance until OR records a DEFERRED decision or the item reaches GREEN")
        else:
            errors.append(f"{item_id} TDD state is {state}; expected GREEN_CONFIRMED or DEFERRED before executor result")
    return errors


def assert_tdd_complete(mode: dict[str, Any]) -> None:
    errors = tdd_completion_errors(mode)
    if errors:
        raise StateError("G4 TDD gate blocked: " + "; ".join(errors))


def is_ui_work_item(item: dict[str, Any]) -> bool:
    if str(item.get("kind") or "").lower() == "ui":
        return True
    frame_ids = [str(value).strip() for value in item.get("frame_ids") or [] if str(value).strip()]
    if frame_ids and any(frame_id != "NO_UI" for frame_id in frame_ids):
        return True
    return bool(item.get("spec_refs"))


def work_item_guidance_contract(item: dict[str, Any]) -> str:
    parts: list[str] = []
    frame_ids = [str(value) for value in item.get("frame_ids") or [] if str(value).strip()]
    if frame_ids and frame_ids != ["NO_UI"]:
        parts.append("G2 UI frames=" + ",".join(frame_ids))
    contract_ref = str(item.get("contract_ref") or "").strip()
    if contract_ref:
        parts.append("G2 pencil_contract=" + contract_ref)
    spec_refs = item.get("spec_refs") if isinstance(item.get("spec_refs"), dict) else {}
    if spec_refs:
        refs = [f"{key}:{value}" for key, value in spec_refs.items() if value]
        if refs:
            parts.append("G2 design specs=" + "; ".join(refs))
    evidence_refs = item.get("evidence_refs") if isinstance(item.get("evidence_refs"), dict) else {}
    if evidence_refs:
        refs = [f"{key}:{value}" for key, value in evidence_refs.items() if value]
        if refs:
            parts.append("visual evidence=" + "; ".join(refs))
    checks = [str(value).strip() for value in item.get("acceptance_checks") or [] if str(value).strip()]
    if checks:
        parts.append("acceptance=" + " | ".join(checks[:3]))
    code_targets = [str(value).strip() for value in item.get("code_targets") or [] if str(value).strip()]
    if code_targets:
        parts.append("planned code_targets=" + ",".join(code_targets[:8]))
    return " ".join(parts)


def active_work_item(mode: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        return None
    try:
        return _active_item(tdd)
    except StateError:
        return None


def mark_active_ui_guidance(mode: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    active = active_work_item(mode)
    if active is None:
        return None
    item_id, item = active
    if not is_ui_work_item(item):
        return None
    guidance = {
        "recorded_at": utc_now(),
        "work_item_id": item_id,
        "source": source,
        "contract": work_item_guidance_contract(item),
        "frame_ids": list(item.get("frame_ids") or []),
        "spec_refs": item.get("spec_refs") if isinstance(item.get("spec_refs"), dict) else {},
        "evidence_refs": item.get("evidence_refs") if isinstance(item.get("evidence_refs"), dict) else {},
        "acceptance_checks": list(item.get("acceptance_checks") or []),
        "code_targets": list(item.get("code_targets") or []),
    }
    item["ui_guidance"] = guidance
    return guidance


def ui_guidance_errors(mode: dict[str, Any]) -> list[str]:
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        return []
    errors: list[str] = []
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    for item_id in tdd.get("work_item_order") or []:
        item = items.get(item_id, {})
        if not is_ui_work_item(item):
            continue
        if item.get("state") == GREEN_CONFIRMED and not item.get("ui_guidance"):
            errors.append(f"{item_id} is a UI work item but has no pre-implementation G2/G3 UI guidance record")
    return errors


def assert_ui_guidance_complete(mode: dict[str, Any]) -> None:
    errors = ui_guidance_errors(mode)
    if errors:
        raise StateError("G4 UI guidance gate blocked: " + "; ".join(errors))


def _find_item_section(text: str, item_id: str) -> str:
    pattern = re.compile(
        rf"(?ms)^##\s+(?:Work Item|Feature)[^\n]*\b{re.escape(item_id)}\b[^\n]*\n(?P<body>.*?)(?=^##\s|\Z)"
    )
    match = pattern.search(text)
    return match.group("body") if match else ""


def execution_tdd_evidence_errors(mode: dict[str, Any], text: str) -> list[str]:
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        return []
    errors: list[str] = []
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    for item_id in tdd.get("work_item_order") or []:
        item = items.get(item_id, {})
        if item.get("state") != GREEN_CONFIRMED:
            continue
        body = _find_item_section(text, item_id)
        if not body:
            errors.append(f"05-execution.md is missing a Work Item/Feature section for {item_id}")
            continue
        if not re.search(r"(?i)\bRED\b|RED evidence|failing test", body):
            errors.append(f"05-execution.md section {item_id} is missing RED evidence")
        if not re.search(r"(?i)\bGREEN\b|GREEN evidence|passing test", body):
            errors.append(f"05-execution.md section {item_id} is missing GREEN evidence")
    if not re.search(r"(?i)tdd[_\s-]*(?:exception\s+in\s+effect|exception)?\s*:\s*(YES|NO)", text):
        errors.append("05-execution.md Execution Summary must state TDD exception: YES or NO")
    return errors


def _evidence_lines(prefix: str, evidence: dict[str, Any] | None) -> list[str]:
    if not isinstance(evidence, dict):
        return [f"- {prefix}: missing"]
    return [
        f"- Command: {evidence.get('command') or 'not recorded'}",
        f"- Test file: {evidence.get('test_file') or 'not recorded'}",
        f"- Result: {evidence.get('passed')} passed, {evidence.get('failed')} failed",
        f"- Output sha: {evidence.get('output_sha256') or 'not recorded'}",
        f"- Output excerpt: {evidence.get('output_excerpt') or 'not recorded'}",
    ]


def render_tdd_execution_markdown(mode: dict[str, Any]) -> list[str]:
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        return ["## Execution Summary", "", "- TDD exception: NO", "- TDD status: not_required"]
    lines: list[str] = ["## Work Items", ""]
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    completed = 0
    deferred = 0
    for item_id in tdd.get("work_item_order") or []:
        item = items.get(item_id, {})
        state = item.get("state")
        if state == GREEN_CONFIRMED:
            completed += 1
            status = "COMPLETE"
        elif state == DEFERRED:
            deferred += 1
            status = "DEFERRED"
        else:
            status = str(state or "PENDING")
        lines.extend(
            [
                f"## Work Item: {item_id} - {item.get('title') or item_id}",
                "",
                f"Status: {status}",
                "",
                "### G2/G3 UI guidance",
                "",
            ]
        )
        guidance = item.get("ui_guidance") if isinstance(item.get("ui_guidance"), dict) else None
        if guidance:
            lines.extend(
                [
                    f"- Source: {guidance.get('source') or 'hook-trace'}",
                    f"- Frames: {', '.join(str(value) for value in guidance.get('frame_ids') or []) or 'NO_UI'}",
                    f"- Specs: {guidance.get('spec_refs') or {}}",
                    f"- Acceptance: {' | '.join(str(value) for value in guidance.get('acceptance_checks') or []) or 'not recorded'}",
                    "",
                ]
            )
        elif is_ui_work_item(item):
            lines.extend(["- Missing pre-implementation G2/G3 UI guidance.", ""])
        else:
            lines.extend(["- NO_UI", ""])
        lines.extend(
            [
                "### RED evidence",
                "",
                *_evidence_lines("RED", item.get("red_evidence")),
                "",
                "### GREEN evidence",
                "",
                *_evidence_lines("GREEN", item.get("green_evidence")),
                "",
                "### REFACTOR",
                "",
                "- Suite still green: YES",
                "",
                "### Files changed in this work item",
                "",
            ]
        )
        targets = item.get("code_targets") if isinstance(item.get("code_targets"), list) else []
        lines.extend([f"- {target}" for target in targets] or ["- not recorded"])
        lines.append("")
    total = len(tdd.get("work_item_order") or [])
    lines.extend(
        [
            "## Execution Summary",
            "",
            f"- Work items completed: {completed} of {total}",
            f"- Work items deferred: {deferred}",
            "- Work items blocked: 0",
            "- TDD exception: NO",
            f"- TDD status: {tdd.get('status')}",
        ]
    )
    return lines


def paths_from_payload(payload: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def add(value: str) -> None:
        clean = value.strip().strip("`\"'")
        if clean and clean not in found:
            found.append(clean)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str) and re.search(r"(?i)(path|file|target|patch|command)", str(key)):
                    add(child)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            for match in PATCH_FILE_RE.finditer(value):
                add(match.group("path"))
            for match in PATH_TOKEN_RE.finditer(value):
                add(match.group("path"))

    walk(payload)
    return found


def production_code_paths_from_payload(payload: dict[str, Any]) -> list[str]:
    paths = paths_from_payload(payload)
    return [path for path in paths if is_production_code_path(path)]


def write_block_message(mode: dict[str, Any], payload: dict[str, Any]) -> str | None:
    targets = production_code_paths_from_payload(payload)
    if not targets:
        return None
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        return None
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    active_id = tdd.get("active_work_item_id")
    if not active_id:
        return (
            "SuperTeam Codex blocked production-code write because G4 TDD is complete or has no active work item. "
            f"Targets: {', '.join(targets)}."
        )
    item = items.get(active_id, {})
    state = item.get("state")
    if state == PENDING:
        return (
            f"SuperTeam Codex blocked production-code write for {active_id}: state=PENDING. "
            "Record a failing RED test through g4-trace --signal tdd-red before editing production code. "
            f"Targets: {', '.join(targets)}."
        )
    if state == GREEN_CONFIRMED:
        return (
            f"SuperTeam Codex blocked production-code write for {active_id}: state=GREEN_CONFIRMED. "
            "Use g4-trace --signal tdd-next before starting the next work item. "
            f"Targets: {', '.join(targets)}."
        )
    if state in {BLOCKED, DEFERRED}:
        return (
            f"SuperTeam Codex blocked production-code write for {active_id}: state={state}. "
            "Use g4-trace --signal tdd-next or resolve the escalation before writing production code. "
            f"Targets: {', '.join(targets)}."
        )
    if state == RED_LOCKED:
        attempts = int(item.get("green_attempts") or 0)
        if attempts >= 3:
            return f"SuperTeam Codex blocked production-code write for {active_id}: three GREEN attempts failed; record BLOCKED escalation."
        return None
    return f"SuperTeam Codex blocked production-code write for {active_id}: unknown TDD state {state!r}."


def write_guidance_message(mode: dict[str, Any], payload: dict[str, Any]) -> str | None:
    targets = production_code_paths_from_payload(payload)
    if not targets:
        return None
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        return None
    items = tdd.get("items") if isinstance(tdd.get("items"), dict) else {}
    active_id = tdd.get("active_work_item_id")
    if not active_id:
        return (
            "SuperTeam Codex G4 guidance: TDD is complete or has no active work item. "
            "Further implementation will not be accepted unless G4 TDD state is reopened. "
            f"Targets: {', '.join(targets)}."
        )
    item = items.get(active_id, {})
    state = item.get("state")
    contract = work_item_guidance_contract(item)
    if state == PENDING:
        return (
            f"SuperTeam Codex G4 guidance for {active_id}: state=PENDING. "
            "Next required hook-trace step is tdd-red; executor result will be rejected until RED/GREEN evidence exists. "
            f"{contract + ' ' if contract else ''}Targets: {', '.join(targets)}."
        )
    if state == RED_LOCKED:
        return (
            f"SuperTeam Codex G4 guidance for {active_id}: state=RED_LOCKED. "
            "Implement the smallest change, run the test, then record tdd-green when it passes. "
            f"{contract + ' ' if contract else ''}Targets: {', '.join(targets)}."
        )
    if state == GREEN_CONFIRMED:
        return (
            f"SuperTeam Codex G4 guidance for {active_id}: state=GREEN_CONFIRMED. "
            "Use tdd-next before starting another work item; extra changes will fail G4 acceptance unless they are tied to a reopened TDD item. "
            f"{contract + ' ' if contract else ''}Targets: {', '.join(targets)}."
        )
    if state in {BLOCKED, DEFERRED}:
        return (
            f"SuperTeam Codex G4 guidance for {active_id}: state={state}. "
            "Use tdd-next or resolve the escalation before claiming G4 completion. "
            f"{contract + ' ' if contract else ''}Targets: {', '.join(targets)}."
        )
    return f"SuperTeam Codex G4 guidance for {active_id}: unknown TDD state {state!r}."


def _parse_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def parse_test_counts(output: str) -> tuple[int | None, int | None, bool]:
    failed = _parse_int(r"(\d+)\s+failed", output)
    passed = _parse_int(r"(\d+)\s+passed", output)
    if failed is None and re.search(r"(?i)\bFAIL(?:ED)?\b", output):
        failed = 1
    if passed is None and re.search(r"(?i)\bPASS(?:ED)?\b", output):
        passed = 1
    if passed is not None and failed is None:
        failed = 0
    if failed is not None and passed is None:
        passed = 0
    is_error = bool(re.search(r"(?i)\b(error|exception|traceback)\b", output))
    return passed, failed, is_error


def observe_test_result(mode: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    text = str(payload.get("command") or payload.get("input") or payload.get("cmd") or "")
    if not TEST_COMMAND_RE.search(text):
        return None
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    output = "\n".join(
        str(part or "")
        for part in [
            payload.get("stdout"),
            payload.get("stderr"),
            payload.get("output"),
            response.get("stdout") if isinstance(response, dict) else "",
            response.get("stderr") if isinstance(response, dict) else "",
        ]
    )
    passed, failed, is_error = parse_test_counts(output)
    tdd = ensure_tdd_state(mode)
    if not tdd.get("required"):
        return None
    try:
        active_id, item = _active_item(tdd)
    except StateError:
        return None
    state = item.get("state")
    if state == PENDING and failed and failed > 0 and not is_error:
        return apply_tdd_signal(
            mode,
            "tdd-red",
            output,
            command=text,
            passed=passed,
            failed=failed,
            source="post-tool-test-observer",
        )
    if state == RED_LOCKED and failed == 0 and passed and passed > 0:
        return apply_tdd_signal(
            mode,
            "tdd-green",
            output,
            command=text,
            passed=passed,
            failed=0,
            source="post-tool-test-observer",
        )
    if state == RED_LOCKED and failed and failed > 0:
        item["green_attempts"] = int(item.get("green_attempts") or 0) + 1
        return {"work_item_id": active_id, "state": RED_LOCKED, "status": tdd.get("status"), "green_attempts": item["green_attempts"]}
    return None
