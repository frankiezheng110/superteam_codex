from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import load_mode, validate_mode
from .workspace import Workspace, detect_version_dirs, read_json


def _check(name: str, status: str, message: str, data: dict | None = None) -> dict:
    item = {"name": name, "status": status, "message": message}
    if data:
        item["data"] = data
    return item


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

