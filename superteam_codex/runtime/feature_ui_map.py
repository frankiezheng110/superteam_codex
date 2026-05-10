from __future__ import annotations

import re
from pathlib import Path

from .workspace import rel_to, write_json, write_text


TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
UI_HINTS = (
    "pencil",
    "frame",
    "ui",
    "screen",
    "page",
    "界面",
    "页面",
    "设计",
    "帧",
)
FRAME_REF_RE = re.compile(
    r"\b(?:"
    r"(?:pencil\s+frame|frame)\s+(?:is\s+)?`([A-Za-z][A-Za-z0-9_-]{3,31})`|"
    r"(?:pencil\s+frame|frame)\s*(?:[:=#]|->)\s*`?([A-Za-z][A-Za-z0-9_-]{3,31})`?|"
    r"(?:frame_id|frame-id|id)\s*[:=]\s*`?([A-Za-z][A-Za-z0-9_-]{3,31})`?"
    r")",
    re.IGNORECASE,
)
COMMON_FALSE_TOKENS = {
    "TODO",
    "DONE",
    "PASS",
    "FAIL",
    "PENDING",
    "Pencil",
    "Frame",
    "Source",
    "Task",
    "Plan",
    "Design",
    "Feature",
    "Screen",
    "NO_UI",
    "event_tree",
    "g2_contract",
    "frame_inventory",
    "feature_ui_map",
}


def _frame_reference_candidates(line: str) -> set[str]:
    candidates: set[str] = set()
    for match in FRAME_REF_RE.finditer(line):
        candidates.update(value for value in match.groups() if value)
    return candidates


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def build_feature_ui_map(manifest: dict, inventory: dict) -> dict:
    project_root = Path(manifest["project_root"]).resolve()
    frame_ids = {frame["id"] for frame in inventory.get("frames", [])}
    references: dict[str, list[dict]] = {frame_id: [] for frame_id in sorted(frame_ids)}
    missing: dict[str, list[dict]] = {}
    scanned_files: list[str] = []

    for item in manifest.get("files", []):
        path = Path(item["absolute_path"])
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.exists():
            continue
        rel = rel_to(path, project_root)
        scanned_files.append(rel)
        for line_no, line in enumerate(_read_lines(path), start=1):
            lower = line.lower()
            for frame_id in frame_ids:
                if frame_id in line:
                    references[frame_id].append(
                        {
                            "file": rel,
                            "line": line_no,
                            "snippet": line.strip()[:240],
                        }
                    )
            if not any(hint in lower for hint in UI_HINTS):
                continue
            candidates = _frame_reference_candidates(line)
            for token in candidates:
                if token in COMMON_FALSE_TOKENS or token in frame_ids:
                    continue
                if token.lower() in {value.lower() for value in COMMON_FALSE_TOKENS}:
                    continue
                missing.setdefault(token, []).append(
                    {
                        "file": rel,
                        "line": line_no,
                        "snippet": line.strip()[:240],
                    }
                )

    referenced = {frame_id: hits for frame_id, hits in references.items() if hits}
    if inventory.get("frame_count", 0) == 0:
        status = "no_ui_inventory"
    elif missing:
        status = "blocked_missing_frames"
    elif not referenced:
        status = "needs_explicit_mapping"
    else:
        status = "ok"

    return {
        "schema": "superteam_codex.feature_ui_map.v1",
        "project_root": str(project_root),
        "status": status,
        "scanned_files": scanned_files,
        "frame_count": inventory.get("frame_count", 0),
        "mapped_frame_count": len(referenced),
        "references": referenced,
        "missing_frame_references": missing,
    }


def write_feature_ui_map(run_dir: Path, mapping: dict) -> None:
    write_json(run_dir / "feature-ui-map.json", mapping)
    lines = [
        "# Feature UI Map",
        "",
        f"Status: `{mapping['status']}`",
        f"Frames discovered: {mapping['frame_count']}",
        f"Frames referenced by source docs: {mapping['mapped_frame_count']}",
        "",
    ]
    if mapping["references"]:
        lines.extend(["## Mapped Frames", ""])
        for frame_id, hits in sorted(mapping["references"].items()):
            lines.append(f"### `{frame_id}`")
            for hit in hits[:10]:
                lines.append(f"- `{hit['file']}:{hit['line']}` {hit['snippet']}")
            lines.append("")
    if mapping["missing_frame_references"]:
        lines.extend(["## Missing Frame References", ""])
        for token, hits in sorted(mapping["missing_frame_references"].items()):
            lines.append(f"### `{token}`")
            for hit in hits[:10]:
                lines.append(f"- `{hit['file']}:{hit['line']}` {hit['snippet']}")
            lines.append("")
    if not mapping["references"] and not mapping["missing_frame_references"]:
        lines.append("No explicit feature-to-frame references were found.")
    write_text(run_dir / "03-feature-ui-map.md", "\n".join(lines).rstrip() + "\n")
