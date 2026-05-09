from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from superteam_codex.runtime.event_tree import activate_event
from superteam_codex.runtime.hooks import handle_event
from superteam_codex.runtime.stages import start_run
from superteam_codex.runtime.state import load_mode, save_mode, set_lifecycle, set_stage
from superteam_codex.runtime.workspace import Workspace


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class HookTests(unittest.TestCase):
    def copy_fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / "sms_minimal"
        shutil.copytree(FIXTURES / "sms_minimal", root)
        return temp, root

    def test_hook_manifest_uses_codex_event_names(self) -> None:
        manifest = json.loads((Path(__file__).resolve().parents[1] / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest["hooks"]),
            {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Stop"},
        )

    def test_blocks_product_write_before_execute(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        start_run(Workspace(root), "Hook write test")

        code, message = handle_event(
            "preToolUse",
            {
                "cwd": str(root),
                "tool": "apply_patch",
                "path": str(root / "src" / "App.vue"),
            },
        )

        self.assertEqual(code, 2)
        self.assertIn("before execute", message)

    def test_allows_state_write_before_execute(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        start_run(Workspace(root), "Hook state write test")

        code, message = handle_event(
            "PreToolUse",
            {
                "cwd": str(root),
                "tool": "apply_patch",
                "path": str(root / ".superteam_codex" / "runs" / "x" / "01-project-definition.md"),
            },
        )

        self.assertEqual(code, 0)
        self.assertEqual(message, "")

    def test_blocks_nested_superteam_run_inside_active_run(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        start_run(Workspace(root), "Hook nested run test")

        code, message = handle_event(
            "UserPromptSubmit",
            {
                "cwd": str(root),
                "prompt": "$superteam:go implement one small button",
            },
        )

        self.assertEqual(code, 2)
        self.assertIn("nested run", message)

    def test_stop_guard_blocks_active_execute(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Hook stop test")
        set_stage(ws, "execute", "in_progress", force=True)

        code, message = handle_event("Stop", {"cwd": str(root)})

        self.assertEqual(code, 2)
        self.assertIn("still active", message)

    def test_stop_guard_allows_paused_run(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Hook paused test")
        set_stage(ws, "execute", "in_progress", force=True)
        set_lifecycle(ws, "paused", "paused_by_test")

        code, message = handle_event("Stop", {"cwd": str(root)})

        self.assertEqual(code, 0)
        self.assertEqual(message, "")

    def test_g2_allows_pencil_write_only_during_pencil_design_event_and_audits(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Hook G2 Pencil design test")
        set_stage(ws, "g2", "designing", force=True)
        mode = load_mode(ws)
        assert mode is not None
        activate_event(mode, "G2.DESIGN_PENCIL_STEPS")
        save_mode(ws, mode)

        code, message = handle_event(
            "PreToolUse",
            {
                "cwd": str(root),
                "tool": "shell_command",
                "command": "Set-Content pencil/app.pen '{}'",
            },
        )

        self.assertEqual(code, 0)
        self.assertEqual(message, "")
        audit = root / ".superteam_codex" / "state" / "hook-events.jsonl"
        self.assertTrue(audit.exists())
        self.assertIn("G2.DESIGN_PENCIL_STEPS", audit.read_text(encoding="utf-8"))
        mode = load_mode(ws)
        assert mode is not None
        hooks = [item["hook"] for item in mode.get("hook_trace", [])]
        self.assertIn("PreToolUse", hooks)

    def test_g2_blocks_non_pencil_write_during_pencil_design_event(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Hook G2 non-pencil write test")
        set_stage(ws, "g2", "designing", force=True)
        mode = load_mode(ws)
        assert mode is not None
        activate_event(mode, "G2.DESIGN_PENCIL_STEPS")
        save_mode(ws, mode)

        code, message = handle_event(
            "PreToolUse",
            {
                "cwd": str(root),
                "tool": "apply_patch",
                "path": str(root / "src" / "App.vue"),
            },
        )

        self.assertEqual(code, 2)
        self.assertIn("active_leaf_event=G2.DESIGN_PENCIL_STEPS", message)

    def test_g2_blocks_pencil_batch_design_outside_design_step(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Hook G2 Pencil batch outside design test")
        set_stage(ws, "g2", "planning", force=True)
        mode = load_mode(ws)
        assert mode is not None
        activate_event(mode, "G2.DRAFT_UI_DESIGN_PLAN")
        save_mode(ws, mode)

        code, message = handle_event(
            "PreToolUse",
            {
                "cwd": str(root),
                "tool": "mcp__pencil__batch_design",
                "filePath": str(root / "pencil" / "sms-master.pen"),
                "operations": "frame=I(document,{type:\"frame\"})",
            },
        )

        self.assertEqual(code, 2)
        self.assertIn("active_leaf_event=G2.DRAFT_UI_DESIGN_PLAN", message)

    def test_g2_allows_pencil_batch_design_inside_design_step(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Hook G2 Pencil batch inside design test")
        set_stage(ws, "g2", "designing", force=True)
        mode = load_mode(ws)
        assert mode is not None
        activate_event(mode, "G2.DESIGN_PENCIL_STEPS")
        save_mode(ws, mode)

        code, message = handle_event(
            "PreToolUse",
            {
                "cwd": str(root),
                "tool": "mcp__pencil__batch_design",
                "filePath": str(root / "pencil" / "sms-master.pen"),
                "operations": "frame=I(document,{type:\"frame\"})",
            },
        )

        self.assertEqual(code, 0)
        self.assertEqual(message, "")

    def test_execute_tdd_guides_production_write_before_red_and_after_green(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Hook G4 TDD write gate test")
        set_stage(ws, "execute", "g4_tdd_test", force=True)
        mode = load_mode(ws)
        assert mode is not None
        mode["g4_contract"] = {
            "status": "pending",
            "execution_plan": {
                "work_items": [
                    {
                        "id": "WI-001",
                        "kind": "ui",
                        "title": "App implementation",
                        "frame_ids": ["frame-login"],
                        "spec_refs": {"layout": "ui-layout-spec.json#frames.frame-login"},
                        "acceptance_checks": ["UI matches Pencil frame `frame-login`"],
                        "code_targets": ["src/App.vue"],
                        "verification_commands": ["npm run test"],
                    }
                ]
            },
            "executor": None,
            "execution_evidence": None,
            "polish": None,
            "tdd": {
                "required": True,
                "status": "active",
                "active_work_item_id": "WI-001",
                "work_item_order": ["WI-001"],
                "items": {
                    "WI-001": {
                        "id": "WI-001",
                        "kind": "ui",
                        "title": "App implementation",
                        "state": "PENDING",
                        "red_evidence": None,
                        "green_evidence": None,
                        "green_attempts": 0,
                        "frame_ids": ["frame-login"],
                        "spec_refs": {"layout": "ui-layout-spec.json#frames.frame-login"},
                        "acceptance_checks": ["UI matches Pencil frame `frame-login`"],
                        "code_targets": ["src/App.vue"],
                        "production_code_targets": ["src/App.vue"],
                        "verification_commands": ["npm run test"],
                    }
                },
            },
        }
        save_mode(ws, mode)

        code, message = handle_event(
            "PreToolUse",
            {
                "cwd": str(root),
                "tool": "apply_patch",
                "path": str(root / "src" / "App.vue"),
            },
        )
        self.assertEqual(code, 0)
        self.assertIn("state=PENDING", message)
        self.assertIn("G3 UI frames=frame-login", message)
        self.assertIn("ui-layout-spec.json#frames.frame-login", message)

        mode = load_mode(ws)
        assert mode is not None
        mode["g4_contract"]["tdd"]["items"]["WI-001"]["state"] = "RED_LOCKED"
        save_mode(ws, mode)
        code, message = handle_event(
            "PreToolUse",
            {
                "cwd": str(root),
                "tool": "apply_patch",
                "path": str(root / "src" / "App.vue"),
            },
        )
        self.assertEqual(code, 0)
        self.assertIn("state=RED_LOCKED", message)

        mode = load_mode(ws)
        assert mode is not None
        mode["g4_contract"]["tdd"]["items"]["WI-001"]["state"] = "GREEN_CONFIRMED"
        save_mode(ws, mode)
        code, message = handle_event(
            "PreToolUse",
            {
                "cwd": str(root),
                "tool": "apply_patch",
                "path": str(root / "src" / "App.vue"),
            },
        )
        self.assertEqual(code, 0)
        self.assertIn("GREEN_CONFIRMED", message)

    def test_execute_post_tool_observer_advances_tdd_state_from_test_output(self) -> None:
        temp, root = self.copy_fixture()
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Hook G4 TDD observer test")
        set_stage(ws, "execute", "g4_tdd_observer_test", force=True)
        mode = load_mode(ws)
        assert mode is not None
        mode["g4_contract"] = {
            "status": "pending",
            "execution_plan": {
                "work_items": [
                    {
                        "id": "WI-001",
                        "title": "App implementation",
                        "code_targets": ["src/App.vue"],
                        "verification_commands": ["npm run test"],
                    }
                ]
            },
            "executor": None,
            "execution_evidence": None,
            "polish": None,
            "tdd": {
                "required": True,
                "status": "active",
                "active_work_item_id": "WI-001",
                "work_item_order": ["WI-001"],
                "items": {
                    "WI-001": {
                        "id": "WI-001",
                        "title": "App implementation",
                        "state": "PENDING",
                        "red_evidence": None,
                        "green_evidence": None,
                        "green_attempts": 0,
                        "code_targets": ["src/App.vue"],
                        "production_code_targets": ["src/App.vue"],
                        "verification_commands": ["npm run test"],
                    }
                },
            },
        }
        save_mode(ws, mode)

        code, message = handle_event(
            "PostToolUse",
            {
                "cwd": str(root),
                "tool": "shell_command",
                "command": "npm run test",
                "stdout": "1 failed",
            },
        )
        self.assertEqual(code, 0)
        self.assertEqual(message, "")
        mode = load_mode(ws)
        assert mode is not None
        self.assertEqual(mode["g4_contract"]["tdd"]["items"]["WI-001"]["state"], "RED_LOCKED")

        code, message = handle_event(
            "PostToolUse",
            {
                "cwd": str(root),
                "tool": "shell_command",
                "command": "npm run test",
                "stdout": "1 passed",
            },
        )
        self.assertEqual(code, 0)
        self.assertEqual(message, "")
        mode = load_mode(ws)
        assert mode is not None
        self.assertEqual(mode["g4_contract"]["tdd"]["items"]["WI-001"]["state"], "GREEN_CONFIRMED")


if __name__ == "__main__":
    unittest.main()
