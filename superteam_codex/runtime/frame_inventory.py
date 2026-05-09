from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .workspace import rel_to, write_json, write_text


@dataclass(frozen=True)
class FrameRecord:
    id: str
    name: str
    type: str
    path: str
    source_file: str
    width: float | int | None = None
    height: float | int | None = None


def _walk_json(node: Any, source_file: str, parent_path: list[str]) -> list[FrameRecord]:
    records: list[FrameRecord] = []
    if isinstance(node, dict):
        node_id = node.get("id")
        node_type = node.get("type")
        name = str(node.get("name") or node_id or "")
        current_path = parent_path + ([str(node_id)] if node_id else [])
        if node_id and node_type == "frame":
            records.append(
                FrameRecord(
                    id=str(node_id),
                    name=name,
                    type=str(node_type),
                    path="/".join(current_path),
                    source_file=source_file,
                    width=node.get("width"),
                    height=node.get("height"),
                )
            )
        for value in node.values():
            if isinstance(value, (dict, list)):
                records.extend(_walk_json(value, source_file, current_path))
    elif isinstance(node, list):
        for value in node:
            records.extend(_walk_json(value, source_file, parent_path))
    return records


def _regex_fallback(text: str, source_file: str) -> list[FrameRecord]:
    records: list[FrameRecord] = []
    pattern = re.compile(
        r'"id"\s*:\s*"(?P<id>[A-Za-z0-9_-]+)".{0,240}?"type"\s*:\s*"frame"',
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        records.append(
            FrameRecord(
                id=match.group("id"),
                name=match.group("id"),
                type="frame",
                path=match.group("id"),
                source_file=source_file,
            )
        )
    return records


def extract_frames_from_pen(path: Path, project_root: Path) -> list[FrameRecord]:
    source_file = rel_to(path, project_root)
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _regex_fallback(text, source_file)
    return _walk_json(data, source_file, [])


def build_frame_inventory(manifest: dict) -> dict:
    project_root = Path(manifest["project_root"]).resolve()
    records: list[FrameRecord] = []
    for item in manifest.get("files", []):
        if item.get("kind") != "pencil" and not str(item.get("path", "")).lower().endswith(".pen"):
            continue
        path = Path(item["absolute_path"])
        if path.exists():
            records.extend(extract_frames_from_pen(path, project_root))
    dedup: dict[tuple[str, str], FrameRecord] = {}
    for record in records:
        dedup[(record.source_file, record.id)] = record
    frames = sorted(dedup.values(), key=lambda item: (item.source_file.lower(), item.path.lower()))
    return {
        "schema": "superteam_codex.frame_inventory.v1",
        "project_root": str(project_root),
        "frame_count": len(frames),
        "frames": [asdict(item) for item in frames],
    }


def write_frame_inventory(run_dir: Path, inventory: dict) -> None:
    write_json(run_dir / "frame-inventory.json", inventory)
    lines = ["# Pencil Frame Inventory", ""]
    lines.append(f"Frame count: {inventory['frame_count']}")
    lines.extend(["", "## Frames", ""])
    if not inventory["frames"]:
        lines.append("- No Pencil frames discovered.")
    for frame in inventory["frames"]:
        dims = ""
        if frame.get("width") is not None or frame.get("height") is not None:
            dims = f" [{frame.get('width')} x {frame.get('height')}]"
        lines.append(f"- `{frame['id']}` - {frame['name']} ({frame['source_file']}){dims}")
    write_text(run_dir / "frame-inventory.md", "\n".join(lines) + "\n")

