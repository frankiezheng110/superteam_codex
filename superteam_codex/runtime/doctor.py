from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import load_mode, validate_mode
from .visual_evidence import g5_visual_evidence_errors, g6_visual_evidence_errors, is_ui_project
from .workspace import Workspace, detect_version_dirs, read_json


def _check(name: str, status: str, message: str, data: dict | None = None) -> dict:
    item = {"name": name, "status": status, "message": message}
    if data:
        item["data"] = data
    return item


def _contract_check(run_dir: Path, name: str, schema: str) -> dict:
    path = run_dir / name
    data = read_json(path, {})
    if not path.exists():
        return _check(name, "fail", f"{name} is missing", {"path": str(path)})
    if not isinstance(data, dict):
        return _check(name, "fail", f"{name} is not a JSON object", {"path": str(path)})
    if data.get("schema") != schema:
        return _check(name, "fail", f"{name} schema is invalid", {"path": str(path), "schema": data.get("schema")})
    return _check(name, "pass", f"{name} is present", {"path": str(path)})


def _mode_contract(mode: dict[str, Any], name: str) -> dict[str, Any]:
    value = mode.get(name)
    return value if isinstance(value, dict) else {}


def run_doctor(ws: Workspace) -> dict[str, Any]:
    checks: list[dict] = []
    mode = load_mode(ws)
    mode_errors = validate_mode(mode)
    if mode_errors:
        checks.append(_check("mode", "fail", "; ".join(mode_errors)))
        return {"health": "fail", "project_root": str(ws.root), "checks": checks}
    assert mode is not None
    checks.append(_check("mode", "pass", "mode.json is schema-valid"))

    run_dir = Path(mode["run_dir"])
    if run_dir.exists():
        checks.append(_check("run_dir", "pass", "active run directory exists", {"run_dir": str(run_dir)}))
    else:
        checks.append(_check("run_dir", "fail", "active run directory is missing", {"run_dir": str(run_dir)}))

    manifest = read_json(run_dir / "source-manifest.json", {})
    file_count = len(manifest.get("files", []))
    if file_count:
        checks.append(_check("source_pack", "pass", f"{file_count} source files discovered"))
    else:
        checks.append(_check("source_pack", "fail", "no source files discovered"))

    inventory = read_json(run_dir / "frame-inventory.json", {})
    frame_count = int(inventory.get("frame_count", 0) or 0)
    pen_count = int(manifest.get("counts", {}).get("pencil", 0) or 0)
    if pen_count and frame_count == 0:
        checks.append(_check("frame_inventory", "fail", "Pencil files exist but no frames were extracted"))
    elif frame_count:
        checks.append(_check("frame_inventory", "pass", f"{frame_count} Pencil frames discovered"))
    else:
        checks.append(_check("frame_inventory", "warn", "no Pencil UI inventory found"))

    mapping = read_json(run_dir / "feature-ui-map.json", {})
    map_status = mapping.get("status")
    if map_status == "blocked_missing_frames":
        checks.append(
            _check(
                "feature_ui_map",
                "fail",
                "source docs reference missing Pencil frames",
                {"missing": sorted(mapping.get("missing_frame_references", {}).keys())},
            )
        )
    elif map_status == "needs_explicit_mapping":
        checks.append(_check("feature_ui_map", "warn", "Pencil frames exist but source docs do not map features to frames"))
    elif map_status == "ok":
        checks.append(_check("feature_ui_map", "pass", "feature-to-frame references are mapped"))
    else:
        checks.append(_check("feature_ui_map", "warn", f"mapping status is {map_status!r}"))

    versions = detect_version_dirs(ws.root)
    if versions:
        checks.append(_check("version_baseline", "warn", "existing version directories detected", {"latest": versions[-1]}))
    else:
        checks.append(_check("version_baseline", "pass", "no version directories detected"))

    if mode.get("stage") in {"g2", "g3", "execute", "review", "verify", "finish"}:
        checks.append(_contract_check(run_dir, "project-definition.json", "superteam_codex.project_definition.v1"))
    if mode.get("stage") in {"verify", "finish"} or _mode_contract(mode, "g5_contract").get("status") == "done":
        checks.append(_contract_check(run_dir, "review-contract.json", "superteam_codex.review_contract.v1"))
        if is_ui_project(mode):
            visual_errors = g5_visual_evidence_errors(mode)
            checks.append(
                _check(
                    "g5_visual_evidence",
                    "fail" if visual_errors else "pass",
                    "; ".join(visual_errors) if visual_errors else "G5 visual evidence is present",
                )
            )
    if mode.get("stage") == "finish" or _mode_contract(mode, "g6_contract").get("status") == "done":
        checks.append(_contract_check(run_dir, "verification-contract.json", "superteam_codex.verification_contract.v1"))
        if is_ui_project(mode):
            visual_errors = g6_visual_evidence_errors(mode)
            checks.append(
                _check(
                    "g6_visual_evidence",
                    "fail" if visual_errors else "pass",
                    "; ".join(visual_errors) if visual_errors else "G6 visual evidence is present",
                )
            )
    if mode.get("project_lifecycle") == "complete" or _mode_contract(mode, "g7_contract").get("status") == "done":
        checks.append(_contract_check(run_dir, "inspector-audit.json", "superteam_codex.inspector_audit.v1"))
        checks.append(_contract_check(run_dir, "finish-contract.json", "superteam_codex.finish_contract.v1"))

    statuses = {item["status"] for item in checks}
    if "fail" in statuses:
        health = "fail"
    elif "warn" in statuses:
        health = "warn"
    else:
        health = "pass"
    return {
        "health": health,
        "project_root": str(ws.root),
        "active_task_slug": mode.get("active_task_slug"),
        "stage": mode.get("stage"),
        "status": mode.get("status"),
        "checks": checks,
    }
