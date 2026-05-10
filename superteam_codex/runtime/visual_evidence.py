from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import read_json


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
G5_VISUAL_REPORT = "evidence/g5/visual-review-report.json"
G6_VISUAL_REPORT = "evidence/g6/visual-acceptance-report.json"


def _run_dir(mode: dict[str, Any]) -> Path:
    return Path(str(mode["run_dir"]))


def resolve_run_path(mode: dict[str, Any], relative_path: str) -> Path:
    path = Path(str(relative_path))
    if path.is_absolute():
        return path
    return _run_dir(mode) / path


def _load_json_artifact(mode: dict[str, Any], name: str) -> dict[str, Any]:
    data = read_json(resolve_run_path(mode, name), {})
    return data if isinstance(data, dict) else {}


def visual_checks(mode: dict[str, Any]) -> list[dict[str, Any]]:
    visual = _load_json_artifact(mode, "visual-acceptance.json")
    checks = visual.get("checks") if isinstance(visual.get("checks"), list) else []
    return [check for check in checks if isinstance(check, dict)]


def is_ui_project(mode: dict[str, Any]) -> bool:
    ui_map = _load_json_artifact(mode, "ui-code-map.json")
    mappings = ui_map.get("mappings") if isinstance(ui_map.get("mappings"), list) else []
    return ui_map.get("status") == "ok" and bool(mappings)


def _png_file_errors(path: Path, label: str) -> list[str]:
    if not path.exists():
        return [f"{label} is missing: {path}"]
    if not path.is_file():
        return [f"{label} is not a file: {path}"]
    if path.stat().st_size <= len(PNG_SIGNATURE):
        return [f"{label} is empty or too small: {path}"]
    with path.open("rb") as handle:
        if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
            return [f"{label} is not a PNG file: {path}"]
    return []


def reference_screenshot_path(check: dict[str, Any]) -> str:
    pencil = check.get("pencil_reference") if isinstance(check.get("pencil_reference"), dict) else {}
    return str(pencil.get("reference_screenshot") or check.get("reference_screenshot") or "")


def implementation_screenshot_path(check: dict[str, Any]) -> str:
    return str(check.get("implementation_screenshot") or "")


def reference_screenshot_errors(mode: dict[str, Any]) -> list[str]:
    if not is_ui_project(mode):
        return []
    errors: list[str] = []
    for check in visual_checks(mode):
        frame_id = str(check.get("frame_id") or "UNKNOWN")
        reference = reference_screenshot_path(check)
        if not reference:
            errors.append(f"visual-acceptance check {frame_id} has no reference_screenshot")
            continue
        errors.extend(_png_file_errors(resolve_run_path(mode, reference), f"{frame_id} reference screenshot"))
    return errors


def implementation_screenshot_errors(mode: dict[str, Any]) -> list[str]:
    if not is_ui_project(mode):
        return []
    errors: list[str] = []
    for check in visual_checks(mode):
        frame_id = str(check.get("frame_id") or "UNKNOWN")
        implementation = implementation_screenshot_path(check)
        if not implementation:
            errors.append(f"visual-acceptance check {frame_id} has no implementation_screenshot")
            continue
        errors.extend(_png_file_errors(resolve_run_path(mode, implementation), f"{frame_id} implementation screenshot"))
    return errors


def visual_report_errors(mode: dict[str, Any], report_relative_path: str) -> list[str]:
    if not is_ui_project(mode):
        return []
    path = resolve_run_path(mode, report_relative_path)
    if not path.exists():
        return [f"visual comparison report is missing: {path}"]
    report = read_json(path, {})
    if not isinstance(report, dict):
        return [f"visual comparison report is invalid JSON object: {path}"]
    status = str(report.get("status") or "").lower()
    if status not in {"pass", "passed", "ok"}:
        return [f"visual comparison report status must be pass, got {report.get('status')!r}"]
    checks_by_frame: dict[str, dict[str, Any]] = {}
    raw_checks = report.get("checks")
    if isinstance(raw_checks, list):
        for item in raw_checks:
            if isinstance(item, dict) and item.get("frame_id"):
                checks_by_frame[str(item["frame_id"])] = item
    raw_frames = report.get("frames")
    if isinstance(raw_frames, dict):
        for frame_id, item in raw_frames.items():
            if isinstance(item, dict):
                checks_by_frame[str(frame_id)] = item
    errors: list[str] = []
    for check in visual_checks(mode):
        frame_id = str(check.get("frame_id") or "")
        if not frame_id:
            continue
        result = checks_by_frame.get(frame_id)
        if not result:
            errors.append(f"visual comparison report has no result for frame {frame_id}")
            continue
        result_status = str(result.get("status") or "").lower()
        if result_status not in {"pass", "passed", "ok"}:
            errors.append(f"visual comparison for frame {frame_id} did not pass: {result.get('status')!r}")
        max_ratio = ((check.get("comparison") or {}).get("max_pixel_diff_ratio"))
        actual_ratio = result.get("pixel_diff_ratio")
        if isinstance(max_ratio, (int, float)) and isinstance(actual_ratio, (int, float)) and actual_ratio > max_ratio:
            errors.append(f"visual comparison for frame {frame_id} pixel_diff_ratio {actual_ratio} exceeds {max_ratio}")
    return errors


def g4_visual_evidence_errors(mode: dict[str, Any]) -> list[str]:
    return reference_screenshot_errors(mode) + implementation_screenshot_errors(mode)


def g5_visual_evidence_errors(mode: dict[str, Any]) -> list[str]:
    return g4_visual_evidence_errors(mode) + visual_report_errors(mode, G5_VISUAL_REPORT)


def g6_visual_evidence_errors(mode: dict[str, Any]) -> list[str]:
    return g4_visual_evidence_errors(mode) + visual_report_errors(mode, G6_VISUAL_REPORT)
