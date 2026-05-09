from __future__ import annotations

from pathlib import Path
from typing import Any

from .feature_ui_map import build_feature_ui_map, write_feature_ui_map
from .frame_inventory import build_frame_inventory, write_frame_inventory
from .g1 import write_project_definition
from .source_pack import discover_source_pack, write_manifest
from .state import create_mode, create_or_update_project, load_mode, save_mode, validate_mode
from .workspace import Workspace, detect_version_dirs, safe_slug, utc_now, write_text


ARTIFACTS = {
    "02-design.md": "# G2 Design\n\nStatus: pending\n\n## Source Review\n\n- Source pack must be reviewed before implementation.\n- UI-bearing features must map to Pencil frames.\n",
    "04-plan.md": "# G3 Execution Plan\n\nStatus: pending\n\n## Structured Authorities\n\n- `ui-code-map.json` maps Pencil frames to code targets.\n- `ui-layout-spec.json` records Pencil layout structure.\n- `design-tokens.json` records extractable visual tokens.\n- `interaction-state-map.json` records required UI states.\n- `visual-acceptance.json` defines screenshot/layout acceptance checks.\n- `implementation-plan.json` defines G4 work items.\n\n## Required Plan Fields\n\nEach task must cite source files, frame ids or `NO_UI`, changed files, acceptance checks, and evidence commands.\n",
    "05-execution.md": "# Execute\n\nStatus: pending\n\n## Evidence\n\nRecord changed files, source references, frame references, and verification commands here.\n",
    "06-review.md": "# Review\n\nStatus: pending\n\n## Review Gate\n\nReview must challenge source consumption, UI fidelity, behavior coverage, and tests.\n",
    "07-verification.md": "# Verification\n\nStatus: pending\n\n## Verification Gate\n\nVerification must run fresh checks and compare output to the feature UI map.\n",
    "08-finish.md": "# Finish\n\nStatus: pending\n\n## Handoff\n\nSummarize delivered scope, evidence, residual risks, and next action.\n",
}


class StageError(RuntimeError):
    pass


def _unique_slug(ws: Workspace, slug: str) -> str:
    candidate = slug
    n = 2
    while ws.run_dir(candidate).exists():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def create_stage_artifacts(run_dir: Path, task: str) -> None:
    for name, template in ARTIFACTS.items():
        path = run_dir / name
        if not path.exists():
            write_text(path, template.format(task=task))
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(exist_ok=True)


def rebuild_source_and_maps(ws: Workspace, run_dir: Path) -> dict[str, Any]:
    manifest = discover_source_pack(ws)
    write_manifest(run_dir, manifest)
    inventory = build_frame_inventory(manifest)
    write_frame_inventory(run_dir, inventory)
    mapping = build_feature_ui_map(manifest, inventory)
    write_feature_ui_map(run_dir, mapping)
    return {
        "manifest": manifest,
        "inventory": inventory,
        "mapping": mapping,
    }


def start_run(ws: Workspace, task: str, force: bool = False) -> dict[str, Any]:
    ws.ensure()
    existing = load_mode(ws)
    if existing and not force:
        errors = validate_mode(existing)
        if not errors and existing.get("mode") == "active" and existing.get("project_lifecycle") in {"running", "paused"}:
            raise StageError(
                "active SuperTeam Codex run already exists; use resume/status/end/reset or pass --force"
            )
    slug = _unique_slug(ws, safe_slug(task, "superteam-task"))
    run_dir = ws.run_dir(slug)
    run_dir.mkdir(parents=True, exist_ok=False)
    source_result = rebuild_source_and_maps(ws, run_dir)
    create_stage_artifacts(run_dir, task)
    versions = detect_version_dirs(ws.root)
    mode = create_mode(ws, task, slug, run_dir)
    mode["version_baseline"] = {
        "version_dir_count": len(versions),
        "latest": versions[-1] if versions else None,
    }
    mode["source_pack"] = {
        "file_count": len(source_result["manifest"].get("files", [])),
        "pencil_frame_count": source_result["inventory"].get("frame_count", 0),
        "feature_ui_map_status": source_result["mapping"].get("status"),
    }
    save_mode(ws, mode)
    write_project_definition(mode)
    create_or_update_project(ws, slug, task)
    return {
        "ok": True,
        "project_root": str(ws.root),
        "run_slug": slug,
        "run_dir": str(run_dir.resolve()),
        "mode": mode,
        "source_pack": mode["source_pack"],
        "version_baseline": mode["version_baseline"],
    }


def rebuild_active_map(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    errors = validate_mode(mode)
    if errors:
        raise StageError("; ".join(errors))
    assert mode is not None
    run_dir = Path(mode["run_dir"])
    result = rebuild_source_and_maps(ws, run_dir)
    mode["source_pack"] = {
        "file_count": len(result["manifest"].get("files", [])),
        "pencil_frame_count": result["inventory"].get("frame_count", 0),
        "feature_ui_map_status": result["mapping"].get("status"),
    }
    mode["updated_at"] = utc_now()
    save_mode(ws, mode)
    return {
        "ok": True,
        "run_dir": str(run_dir.resolve()),
        "source_pack": mode["source_pack"],
        "mapping_status": result["mapping"].get("status"),
    }


def status_summary(ws: Workspace) -> dict[str, Any]:
    mode = load_mode(ws)
    if not mode:
        return {
            "ok": True,
            "project_root": str(ws.root),
            "active": False,
            "message": "no .superteam_codex mode.json found",
        }
    errors = validate_mode(mode)
    return {
        "ok": not errors,
        "project_root": str(ws.root),
        "active": mode.get("mode") == "active",
        "errors": errors,
        "mode": mode,
    }


def reset_workspace(ws: Workspace, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise StageError("reset requires --confirm; existing state will be moved to a timestamped backup")
    backup = ws.backup_state_dir("reset")
    return {
        "ok": True,
        "project_root": str(ws.root),
        "backup": str(backup.resolve()) if backup else None,
    }
