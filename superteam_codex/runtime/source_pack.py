from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from .workspace import Workspace, file_sha256, rel_to, write_json, write_text


SOURCE_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".pen",
}

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    ".superteam_codex",
    ".superteam",
}

PREFERRED_SOURCE_DIRS = [
    "source-of-truth",
    "sources",
    "source",
    "pencil",
    "plan",
    "docs",
    "requirements",
]


@dataclass(frozen=True)
class SourceFile:
    path: str
    absolute_path: str
    kind: str
    size: int
    sha256: str


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    parts = {part.lower() for part in path.parts}
    if suffix == ".pen":
        return "pencil"
    if "pencil" in parts:
        return "pencil-support"
    if "plan" in parts:
        return "plan"
    if suffix in {".xlsx", ".xls", ".csv", ".tsv"}:
        return "data-fixture"
    if suffix in {".md", ".markdown", ".txt"}:
        return "document"
    if suffix in {".json", ".jsonl", ".yaml", ".yml"}:
        return "structured"
    return "other"


def _walk_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
            yield path


def _candidate_roots(project_root: Path) -> list[Path]:
    preferred = [project_root / name for name in PREFERRED_SOURCE_DIRS if (project_root / name).exists()]
    if preferred:
        return preferred
    return [project_root]


def discover_source_pack(ws: Workspace) -> dict:
    files: list[SourceFile] = []
    seen: set[Path] = set()
    for root in _candidate_roots(ws.root):
        for path in _walk_files(root):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(
                SourceFile(
                    path=rel_to(resolved, ws.root),
                    absolute_path=str(resolved),
                    kind=classify(resolved),
                    size=resolved.stat().st_size,
                    sha256=file_sha256(resolved),
                )
            )
    files = sorted(files, key=lambda item: (item.kind, item.path.lower()))
    counts: dict[str, int] = {}
    for item in files:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return {
        "schema": "superteam_codex.source_manifest.v1",
        "project_root": str(ws.root),
        "source_roots": [rel_to(root.resolve(), ws.root) for root in _candidate_roots(ws.root)],
        "files": [asdict(item) for item in files],
        "counts": counts,
    }


def write_manifest(run_dir: Path, manifest: dict) -> None:
    write_json(run_dir / "source-manifest.json", manifest)
    lines = [
        "# Source Pack",
        "",
        f"Project root: `{manifest['project_root']}`",
        "",
        "## Counts",
        "",
    ]
    if manifest["counts"]:
        for kind, count in sorted(manifest["counts"].items()):
            lines.append(f"- `{kind}`: {count}")
    else:
        lines.append("- No source files discovered.")
    lines.extend(["", "## Files", ""])
    for item in manifest["files"]:
        lines.append(f"- `{item['path']}` ({item['kind']}, {item['size']} bytes)")
    write_text(run_dir / "00-source-pack.md", "\n".join(lines) + "\n")

