from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


SUPER_DIR_NAME = ".superteam_codex"
STATE_SCHEMA = "superteam_codex.mode.v1"
PROJECT_SCHEMA = "superteam_codex.project.v1"


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def safe_slug(text: str, fallback: str = "task", max_len: int = 72) -> str:
    base = text.strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    base = re.sub(r"-{2,}", "-", base).strip("-")
    if not base:
        base = fallback
    return base[:max_len].strip("-") or fallback


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def rel_to(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    @property
    def super_dir(self) -> Path:
        return self.root / SUPER_DIR_NAME

    @property
    def state_dir(self) -> Path:
        return self.super_dir / "state"

    @property
    def runs_dir(self) -> Path:
        return self.super_dir / "runs"

    @property
    def mode_path(self) -> Path:
        return self.state_dir / "mode.json"

    @property
    def project_path(self) -> Path:
        return self.state_dir / "project.json"

    def ensure(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, slug: str) -> Path:
        return self.runs_dir / slug

    def backup_state_dir(self, reason: str = "reset") -> Path | None:
        if not self.super_dir.exists():
            return None
        stamp = utc_now().replace(":", "").replace("+00:00", "Z")
        backup = self.root / f"{SUPER_DIR_NAME}.backup-{stamp}-{safe_slug(reason, 'backup', 24)}"
        n = 2
        candidate = backup
        while candidate.exists():
            candidate = Path(str(backup) + f"-{n}")
            n += 1
        shutil.move(str(self.super_dir), str(candidate))
        return candidate


def find_workspace(start: str | Path | None = None) -> Workspace:
    current = Path(start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for path in [current, *current.parents]:
        if (path / SUPER_DIR_NAME).exists():
            return Workspace(path)
    return Workspace(current)


def detect_version_dirs(root: Path) -> list[dict[str, str]]:
    versions: list[dict[str, str]] = []
    if not root.exists():
        return versions
    pattern = re.compile(r"^V(?P<version>\d+\.\d+\.\d+)(?:_(?P<name>.+))?$")
    for child in root.iterdir():
        if not child.is_dir():
            continue
        match = pattern.match(child.name)
        if match:
            versions.append(
                {
                    "name": child.name,
                    "version": match.group("version"),
                    "path": str(child.resolve()),
                    "label": match.group("name") or "",
                }
            )
    return sorted(versions, key=lambda item: item["version"])

