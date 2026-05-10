from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from superteam_codex.runtime.agent_registry import build_agent_roster, register_agent_call
from superteam_codex.runtime.doctor import run_doctor
from superteam_codex.runtime.g1 import (
    apply_g1_hook_trace_signal,
    approve_g1,
    complete_g1_summary,
    g1_status,
    record_g1_answer,
    run_g1_hook_trace_until_user_gate,
)
from superteam_codex.runtime.g2 import (
    advance_g2,
    apply_g2_hook_trace_signal,
    approve_g2,
    approve_g2_plan,
    g2_status,
    record_g2_design_step,
    run_g2_hook_trace_until_user_gate,
)
from superteam_codex.runtime.g3 import apply_g3_hook_trace_signal, g3_status, run_g3_hook_trace_until_user_gate
from superteam_codex.runtime.g4 import apply_g4_hook_trace_signal, run_g4_hook_trace_until_stage_gate
from superteam_codex.runtime.g5 import apply_g5_hook_trace_signal, review_gate_errors, run_g5_hook_trace_until_stage_gate
from superteam_codex.runtime.g6 import apply_g6_hook_trace_signal, run_g6_hook_trace_until_stage_gate, verification_gate_errors
from superteam_codex.runtime.g7 import (
    apply_g7_hook_trace_signal,
    finish_gate_errors,
    inspector_report_path,
    run_g7_hook_trace_until_stage_gate,
)
from superteam_codex.runtime.stages import refresh_active_event_tree, reset_workspace, start_run, status_summary
from superteam_codex.runtime.state import StateError, load_mode, save_mode, set_lifecycle, set_stage, validate_mode
from superteam_codex.runtime.tdd import code_changing_work_items
from superteam_codex.runtime.workspace import Workspace


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class RuntimeTests(unittest.TestCase):
    PNG_BYTES = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xe2\x26\xb5"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def copy_fixture(self, name: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / name
        shutil.copytree(FIXTURES / name, root)
        return temp, root

    def write_png(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.PNG_BYTES)

    def write_reference_screenshots(self, run_dir: Path, frame_ids: list[str]) -> None:
        for frame_id in frame_ids:
            self.write_png(run_dir / "evidence" / "g2" / "reference" / f"{frame_id}-reference.png")

    def write_implementation_screenshots(self, run_dir: Path, frame_ids: list[str]) -> None:
        for frame_id in frame_ids:
            self.write_png(run_dir / "evidence" / "g6" / f"{frame_id}-implementation.png")

    def write_visual_report(self, run_dir: Path, relative_path: str, frame_ids: list[str], *, status: str = "pass", pixel_diff_ratio: float = 0.0) -> None:
        path = run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "status": status,
                    "checks": [
                        {
                            "frame_id": frame_id,
                            "status": status,
                            "pixel_diff_ratio": pixel_diff_ratio,
                            "reference_screenshot": f"evidence/g2/reference/{frame_id}-reference.png",
                            "implementation_screenshot": f"evidence/g6/{frame_id}-implementation.png",
                        }
                        for frame_id in frame_ids
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def review_contract_payload(self, *, verdict: str = "CLEAR_WITH_CONCERNS", ui_status: str = "pass") -> dict:
        blocked = verdict == "BLOCK"
        scope_status = "block" if blocked else "pass"
        return {
            "schema": "superteam_codex.review_contract.v1",
            "status": "blocked" if blocked else "ok",
            "verdict": verdict,
            "delivery_scope_check": {"status": scope_status, "items": ["WI-001", "WI-002", "WI-003", "WI-004"]},
            "tdd_gate": {"status": "pass", "red_green_evidence": True},
            "checklist_coverage": {"status": scope_status, "covered": True},
            "ui_quality_gate": {"status": ui_status, "frames_checked": ["s1_login", "s2_roster"]},
            "review_artifact": "06-review.md",
        }

    def write_review_contract(self, run_dir: Path, *, verdict: str = "CLEAR_WITH_CONCERNS", ui_status: str = "pass") -> None:
        (run_dir / "review-contract.json").write_text(
            json.dumps(self.review_contract_payload(verdict=verdict, ui_status=ui_status), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def verification_contract_payload(self, *, verdict: str = "PASS", confidence: str = "high", ui_status: str = "pass") -> dict:
        status = "pass" if verdict == "PASS" else "fail" if verdict == "FAIL" else "incomplete"
        return {
            "schema": "superteam_codex.verification_contract.v1",
            "status": status,
            "verdict": verdict,
            "delivery_confidence": confidence,
            "evidence_summary": {"status": status, "fresh": True},
            "requirement_status": {"status": status, "items": ["WI-001", "WI-002", "WI-003", "WI-004"]},
            "test_suite_evidence": {
                "status": status,
                "commands": [{"command": "npm run test:api", "status": status}],
            },
            "ui_evidence": {"status": ui_status, "frames_checked": ["s1_login", "s2_roster"]},
            "verification_artifact": "07-verification.md",
        }

    def write_verification_contract(self, run_dir: Path, *, verdict: str = "PASS", confidence: str = "high", ui_status: str = "pass") -> None:
        (run_dir / "verification-contract.json").write_text(
            json.dumps(
                self.verification_contract_payload(verdict=verdict, confidence=confidence, ui_status=ui_status),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def write_inspector_audit(self, run_dir: Path) -> None:
        (run_dir / "inspector-audit.json").write_text(
            json.dumps(
                {
                    "schema": "superteam_codex.inspector_audit.v1",
                    "status": "pass",
                    "process_audit": {"status": "pass"},
                    "hook_trace_coverage": {"status": "pass"},
                    "event_tree_audit": {"status": "pass"},
                    "agent_boundary_audit": {"status": "pass"},
                    "no_product_code_changes": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def write_finish_contract(self, run_dir: Path) -> None:
        (run_dir / "finish-contract.json").write_text(
            json.dumps(
                {
                    "schema": "superteam_codex.finish_contract.v1",
                    "status": "complete",
                    "verifier_pass_acknowledged": True,
                    "inspector_audit_acknowledged": True,
                    "no_product_code_changes": True,
                    "improvement_action": "keep G6 verifier evidence fresh and keep G7 limited to finish artifacts",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def assert_agent_contract(self, payload: dict, role: str) -> None:
        self.assertTrue(payload["agent_rules_required"])
        definition_path = Path(payload["agent_definition_path"])
        self.assertTrue(definition_path.exists())
        self.assertEqual(definition_path.name, f"{role}.md")
        self.assertEqual(len(payload["rules_sha256"]), 64)
        self.assertEqual(payload["agent_definition_binding"], f"mode.json:agent_roster.roles.{role}")
        self.assertEqual(payload["agent_call_policy"], "initialize_once_then_send_input")
        self.assertIn(str(definition_path), payload["spawn_prompt_contract"])
        self.assertIn(role, payload["spawn_prompt_contract"])
        self.assertTrue(payload["agent_reuse_required"])
        self.assertEqual(payload["agent_slot_role"], role)
        self.assertIn("Do not create event-specific agent names", payload["agent_reuse_instruction"])

    def test_agent_role_slot_rejects_event_specific_respawn_id(self) -> None:
        mode: dict = {"orchestrator": {"agent_calls": []}, "agent_roster": build_agent_roster(), "agent_slots": {}}
        first = register_agent_call(mode, "G1.SUMMARY", "inspector", "agent-inspector", "spawned", "inspect summary")
        self.assertEqual(first["agent_slot_action"], "spawn_new_agent_slot")
        self.assertEqual(first["agent_runtime_action"], "spawn_agent_initial_slot")
        self.assertEqual(first["agent_identity_source"], "mode.json:agent_roster.roles.inspector")

        reused = register_agent_call(mode, "G1.APPROVAL", "inspector", "", "spawned", "inspect approval")
        self.assertEqual(reused["agent_id"], "agent-inspector")
        self.assertEqual(reused["agent_slot_action"], "reuse_existing_agent")
        self.assertEqual(reused["agent_runtime_action"], "send_input")

        with self.assertRaisesRegex(ValueError, "reuse it with send_input"):
            register_agent_call(mode, "G2.REVIEW_SOURCE_PACK", "inspector", "agent-inspector-new", "spawned", "inspect source")

    def test_start_run_initializes_fixed_agent_roster(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        result = start_run(ws, "agent roster validation")
        roster = result["mode"]["agent_roster"]
        self.assertEqual(roster["schema"], "superteam_codex.agent_roster.v1")
        self.assertIn("executor", roster["roles"])
        self.assertIn("reviewer", roster["roles"])
        self.assertIn("verifier", roster["roles"])
        self.assertEqual(roster["roles"]["executor"]["agent_definition_binding"], "mode.json:agent_roster.roles.executor")

    def test_mode_validation_rejects_agent_roster_definition_drift(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "agent roster drift")
        mode = load_mode(ws)
        assert mode is not None
        mode["agent_roster"]["roles"]["executor"]["rules_sha256"] = "0" * 64

        errors = validate_mode(mode)
        self.assertTrue(any("agent_roster.roles.executor.rules_sha256" in error for error in errors))

    def test_mode_validation_rejects_multiple_agent_ids_per_role(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "agent slot validation")
        mode = load_mode(ws)
        assert mode is not None
        mode["agent_slots"] = {"inspector": {"agent_id": "agent-inspector-a"}}
        mode["orchestrator"]["agent_calls"] = [
            {"event": "G1.SUMMARY", "role": "inspector", "agent_id": "agent-inspector-a"},
            {"event": "G1.APPROVAL", "role": "inspector", "agent_id": "agent-inspector-b"},
        ]

        errors = validate_mode(mode)
        self.assertTrue(any("agent role inspector has multiple agent_ids" in error for error in errors))

    def complete_g2_inspector(self, ws: Workspace, note: str = "inspector pass") -> dict:
        status = g2_status(ws)
        event_id = str(status["active_event"])
        apply_g2_hook_trace_signal(
            ws,
            "inspector-spawn-record",
            f"spawn inspector for {event_id}",
            agent="inspector",
            agent_id="agent-inspector",
        )
        return apply_g2_hook_trace_signal(ws, "inspector-result", note, agent="inspector")

    def approve_g2_plan_with_inspector(self, ws: Workspace, note: str = "plan approved") -> dict:
        approve_g2_plan(ws, note=note)
        return self.complete_g2_inspector(ws, "inspector checked G2 UI design plan")

    def complete_g2_design_step_with_inspector(self, ws: Workspace, note: str) -> dict:
        apply_g2_hook_trace_signal(
            ws,
            "spawn-record",
            "spawn designer for Pencil design",
            agent="designer",
            agent_id="agent-designer",
        )
        record_g2_design_step(ws, note, complete=True)
        return self.complete_g2_inspector(ws, "inspector checked Pencil design steps")

    def complete_g3_inspector(self, ws: Workspace, note: str = "inspector pass") -> dict:
        status = g3_status(ws)
        event_id = str(status["active_event"])
        apply_g3_hook_trace_signal(
            ws,
            "inspector-spawn-record",
            f"spawn inspector for {event_id}",
            agent="inspector",
            agent_id="agent-inspector",
        )
        return apply_g3_hook_trace_signal(ws, "inspector-result", note, agent="inspector")

    def complete_g3_spawned_event(self, ws: Workspace, agent: str, agent_id: str, result_note: str) -> dict:
        apply_g3_hook_trace_signal(ws, "spawn-record", f"spawn {agent}", agent=agent, agent_id=agent_id)
        apply_g3_hook_trace_signal(ws, "agent-result", result_note, agent=agent)
        return self.complete_g3_inspector(ws, f"inspector checked {agent}")

    def complete_g4_tdd_cycle(self, ws: Workspace, plan: dict) -> None:
        work_items = code_changing_work_items(plan)
        for index, item in enumerate(work_items):
            item_id = item["id"]
            apply_g4_hook_trace_signal(
                ws,
                "tdd-red",
                f"expected RED for {item_id}",
                work_item_id=item_id,
                command="npm run test:api",
                test_file=f"tests/{item_id}.test.ts",
                passed=0,
                failed=1,
            )
            apply_g4_hook_trace_signal(
                ws,
                "tdd-green",
                f"expected GREEN for {item_id}",
                work_item_id=item_id,
                command="npm run test:api",
                test_file=f"tests/{item_id}.test.ts",
                passed=1,
                failed=0,
            )
            if index < len(work_items) - 1:
                apply_g4_hook_trace_signal(ws, "tdd-next", f"advance after {item_id}", work_item_id=item_id)

    def executor_artifact_text(self, agent_id: str, plan: dict) -> str:
        lines = [
            "---",
            "agent_type: executor",
            f"agent_id: {agent_id}",
            "---",
            "",
            "# G4 Execution",
            "",
            "Status: implementation_complete",
            "",
            "## Executor Result",
            "",
            "- executor-authored evidence",
            "",
        ]
        for item in code_changing_work_items(plan):
            item_id = item["id"]
            lines.extend(
                [
                    f"## Work Item: {item_id} - {item.get('title') or item_id}",
                    "",
                    "Status: COMPLETE",
                    "",
                    "### G2/G3 UI guidance",
                    "",
                    f"- Frames: {', '.join(str(value) for value in item.get('frame_ids') or []) or 'NO_UI'}",
                    f"- Specs: {item.get('spec_refs') or {}}",
                    f"- Acceptance: {' | '.join(str(value) for value in item.get('acceptance_checks') or []) or 'not recorded'}",
                    "",
                    "### RED evidence",
                    "",
                    f"- Command: npm run test:api",
                    f"- Test file: tests/{item_id}.test.ts",
                    "- Result: 0 passed, 1 failed",
                    "- Failure reason: feature not implemented yet",
                    "",
                    "### GREEN evidence",
                    "",
                    "- Command: npm run test:api",
                    f"- Test file: tests/{item_id}.test.ts",
                    "- Result: 1 passed, 0 failed",
                    "- Suite still green: YES",
                    "",
                    "### REFACTOR",
                    "",
                    "- Suite still green: YES",
                    "",
                    "### Files changed in this work item",
                    "",
                ]
            )
            lines.extend([f"- {target}" for target in item.get("code_targets") or []])
            lines.append("")
        lines.extend(["## Execution Summary", "", "- TDD exception: NO", ""])
        return "\n".join(lines)

    def review_artifact_text(self, agent_id: str, task_slug: str) -> str:
        return "\n".join(
            [
                "---",
                "agent_type: reviewer",
                f"agent_id: {agent_id}",
                f"task_slug: {task_slug}",
                "---",
                "",
                "# G5 Review",
                "",
                "Verdict: CLEAR_WITH_CONCERNS",
                "",
                "## Delivery Scope Check",
                "",
                "- WI-001: delivered in 05-execution.md.",
                "- WI-002: delivered in 05-execution.md.",
                "- WI-003: delivered in 05-execution.md.",
                "- WI-004: delivered in 05-execution.md.",
                "",
                "## TDD Gate",
                "",
                "- TDD exception: NO",
                "- RED/GREEN evidence exists for code-changing work items.",
                "",
                "## UI Quality Gate",
                "",
                "- Designer participation required before verification.",
                "- UI fidelity reviewed against Pencil frames, G3 specs, and G4 UI guidance.",
                "",
                "## Checklist Coverage",
                "",
                "- Functional Correctness: checked",
                "- Plan Fidelity: checked",
                "- Code and Design Quality: checked",
                "- Security: checked",
                "- Artifact Completeness: checked",
                "- Error and Fix Quality: checked",
                "- TDD And Test Coverage: checked",
                "- UI Quality: checked",
                "- Immediate Blocker Reporting: checked",
                "",
            ]
        )

    def blocked_review_artifact_text(self, agent_id: str, task_slug: str) -> str:
        return "\n".join(
            [
                "---",
                "agent_type: reviewer",
                f"agent_id: {agent_id}",
                f"task_slug: {task_slug}",
                "---",
                "",
                "# G5 Review",
                "",
                "Verdict: BLOCK",
                "",
                "## Delivery Scope Check",
                "",
                "- WI-003: BLOCK, UI layout does not match the approved Pencil frame.",
                "",
                "## TDD Gate",
                "",
                "- TDD exception: NO",
                "- RED/GREEN evidence exists but the repaired UI work must rerun focused tests.",
                "",
                "## UI Quality Gate",
                "",
                "- Designer participation required before returning to execution.",
                "- UI fidelity is blocked against Pencil frames and G3 specs.",
                "",
                "## Checklist Coverage",
                "",
                "- Functional Correctness: checked",
                "- Plan Fidelity: blocked",
                "- Code and Design Quality: checked",
                "- Security: checked",
                "- Artifact Completeness: checked",
                "- Error and Fix Quality: checked",
                "- TDD And Test Coverage: checked",
                "- UI Quality: blocked",
                "- Immediate Blocker Reporting: checked",
                "",
            ]
        )

    def verification_artifact_text(self, agent_id: str, task_slug: str) -> str:
        return "\n".join(
            [
                "---",
                "agent_type: verifier",
                f"agent_id: {agent_id}",
                f"task_slug: {task_slug}",
                "delivery_confidence: high",
                "---",
                "",
                "# G6 Verification",
                "",
                "Verdict: PASS",
                "",
                "## Evidence Summary",
                "",
                "- Fresh command: npm run test:api",
                "- Result: PASS, 4 passing, 0 failing.",
                "- Review input: 06-review.md was considered but not trusted as final evidence.",
                "",
                "## Requirement Status",
                "",
                "- WI-001: PASS",
                "- WI-002: PASS",
                "- WI-003: PASS",
                "- WI-004: PASS",
                "",
                "## Test Suite Evidence",
                "",
                "- Command: npm run test:api",
                "- Passed: 4",
                "- Failed: 0",
                "",
                "## UI Evidence",
                "",
                "- Pencil frames s1_login and s2_roster were checked against implementation targets.",
                "- Layout, tokens, interaction states, and visual acceptance evidence are PASS.",
                "",
            ]
        )

    def failed_verification_artifact_text(self, agent_id: str, task_slug: str) -> str:
        return "\n".join(
            [
                "---",
                "agent_type: verifier",
                f"agent_id: {agent_id}",
                f"task_slug: {task_slug}",
                "delivery_confidence: low",
                "---",
                "",
                "# G6 Verification",
                "",
                "Verdict: FAIL",
                "",
                "## Evidence Summary",
                "",
                "- Fresh command: npm run test:api",
                "- Result: FAIL, 3 passing, 1 failing.",
                "- Failure: WI-003 UI screenshot does not match Pencil layout.",
                "",
                "## Requirement Status",
                "",
                "- WI-001: PASS",
                "- WI-002: PASS",
                "- WI-003: FAIL",
                "- WI-004: PASS",
                "",
                "## Test Suite Evidence",
                "",
                "- Command: npm run test:api",
                "- Passed: 3",
                "- Failed: 1",
                "",
                "## UI Evidence",
                "",
                "- Pencil frame s1_login failed visual acceptance.",
                "",
            ]
        )

    def inspector_report_text(self, agent_id: str, task_slug: str) -> str:
        return "\n".join(
            [
                "---",
                "agent_type: inspector",
                f"agent_id: {agent_id}",
                f"task_slug: {task_slug}",
                "---",
                "",
                "# G7 Inspector Report",
                "",
                "Status: PASS",
                "",
                "## Process Audit",
                "",
                "- hook_trace guidance was present before G4, G5, G6, and G7 agent work.",
                "- event_tree order was followed from G1 through G7.",
                "- agent role boundaries were preserved.",
                "",
                "## Findings",
                "",
                "- No blocking process defects found.",
                "",
            ]
        )

    def test_ui_visual_gates_reject_missing_screenshots_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            mode = {
                "run_dir": str(run_dir),
                "g5_contract": {
                    "ui_quality": {
                        "required": True,
                        "designer": {"result_note": "PASS: designer compared UI"},
                    }
                },
            }
            (run_dir / "ui-code-map.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "mappings": [{"frame_id": "s1_login", "code_targets": ["src/App.tsx"]}],
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "implementation-plan.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "work_items": [
                            {
                                "id": "WI-001",
                                "kind": "ui",
                                "frame_ids": ["s1_login"],
                                "code_targets": ["src/App.tsx"],
                                "verification_commands": ["npm run build"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "visual-acceptance.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "checks": [
                            {
                                "frame_id": "s1_login",
                                "pencil_reference": {"reference_screenshot": "evidence/g2/reference/s1_login-reference.png"},
                                "implementation_screenshot": "evidence/g6/s1_login-implementation.png",
                                "comparison": {"max_pixel_diff_ratio": 0.02},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            (run_dir / "review-contract.json").write_text(
                json.dumps(self.review_contract_payload(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (run_dir / "verification-contract.json").write_text(
                json.dumps(self.verification_contract_payload(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            review_errors = review_gate_errors(mode, self.review_contract_payload())
            self.assertTrue(any("G5 cannot clear UI review without passing visual evidence" in error for error in review_errors))

            verification_errors = verification_gate_errors(mode, self.verification_contract_payload())
            self.assertTrue(any("G6 cannot PASS UI verification without passing visual evidence" in error for error in verification_errors))

    def test_status_rejects_legacy_text_only_event_tree(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        with temp:
            ws = Workspace(root)
            start_run(ws, "legacy text-only event tree check", force=True)
            mode = load_mode(ws)
            assert mode is not None
            for item in mode["event_tree"]:
                if item.get("id") == "G3.WRITE_PLAN_ARTIFACT":
                    item["id"] = "G3.WRITE_PLAN"
                    item["hook_policy"] = "text_document_only"
                    break
            save_mode(ws, mode)

            status = status_summary(ws)
            self.assertFalse(status["ok"])
            self.assertTrue(any("legacy text-only workflow events" in error for error in status["errors"]))
            self.assertTrue(any("event_tree missing required event: G3.WRITE_PLAN_ARTIFACT" in error for error in status["errors"]))

    def test_repair_event_tree_refreshes_legacy_schema(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        with temp:
            ws = Workspace(root)
            start_run(ws, "repair legacy event tree check", force=True)
            mode = load_mode(ws)
            assert mode is not None
            for item in mode["event_tree"]:
                if item.get("id") == "G3.WRITE_PLAN_ARTIFACT":
                    item["id"] = "G3.WRITE_PLAN"
                    break
            save_mode(ws, mode)

            result = refresh_active_event_tree(ws)
            self.assertTrue(result["ok"])
            self.assertIn("G3.WRITE_PLAN", result["removed_events"])
            self.assertIn("G3.WRITE_PLAN_ARTIFACT", result["added_events"])
            status = status_summary(ws)
            self.assertTrue(status["ok"])
            self.assertEqual(status["mode"]["orchestrator"]["active_event"], "G1.START")

    def test_stage_gates_reject_markdown_without_machine_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            task_slug = "contract-required"
            mode = {
                "run_dir": str(run_dir),
                "project_root": str(run_dir),
                "active_task_slug": task_slug,
                "g5_contract": {
                    "ui_quality": {
                        "required": True,
                        "designer": {"result_note": "PASS: designer compared UI"},
                    }
                },
                "g6_contract": {
                    "verdict": "PASS",
                    "delivery_confidence": "high",
                },
            }
            (run_dir / "implementation-plan.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "work_items": [
                            {
                                "id": "WI-001",
                                "kind": "code",
                                "code_targets": ["src/App.tsx"],
                                "verification_commands": ["npm run test"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "06-review.md").write_text("Verdict: CLEAR\n", encoding="utf-8")
            (run_dir / "07-verification.md").write_text("Verdict: PASS\n", encoding="utf-8")

            review_errors = review_gate_errors(mode)
            self.assertTrue(any("review-contract.json is missing" in error for error in review_errors))

            verification_errors = verification_gate_errors(mode)
            self.assertTrue(any("verification-contract.json is missing" in error for error in verification_errors))

            report_path = inspector_report_path(mode)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(self.inspector_report_text("agent-inspector", task_slug), encoding="utf-8")
            (run_dir / "08-finish.md").write_text("Status: complete\n", encoding="utf-8")
            (run_dir / "retrospective.md").write_text("Improvement: require machine contracts\n", encoding="utf-8")

            finish_errors = finish_gate_errors(mode)
            self.assertTrue(any("inspector-audit.json is missing" in error for error in finish_errors))
            self.assertTrue(any("finish-contract.json is missing" in error for error in finish_errors))

    def finish_artifact_text(self, agent_id: str, task_slug: str) -> str:
        return "\n".join(
            [
                "---",
                "agent_type: writer",
                f"agent_id: {agent_id}",
                f"task_slug: {task_slug}",
                "inspector_report_acknowledged: true",
                "---",
                "",
                "# G7 Finish",
                "",
                "Status: complete",
                "",
                "## Delivery Summary",
                "",
                "- Delivered approved G4 implementation scope.",
                "- Verifier verdict: PASS.",
                "- Inspector report acknowledged before final handoff.",
                "",
                "## Evidence",
                "",
                "- 05-execution.md",
                "- 06-review.md",
                "- 07-verification.md",
                "- inspector report",
                "",
                "## Residual Risks",
                "",
                "- None blocking.",
                "",
            ]
        )

    def retrospective_text(self) -> str:
        return "\n".join(
            [
                "# Retrospective",
                "",
                "improvement_action: keep G6 verifier evidence fresh and keep G7 limited to finish artifacts",
                "",
                "## What Worked",
                "",
                "- Hook guidance led agents with the correct artifacts before work started.",
                "",
            ]
        )

    def test_start_run_detects_missing_pencil_frame(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)

        result = start_run(Workspace(root), "Build SMS from source pack")
        run_dir = Path(result["run_dir"])
        mapping = json.loads((run_dir / "feature-ui-map.json").read_text(encoding="utf-8"))

        self.assertEqual(mapping["status"], "blocked_missing_frames")
        self.assertIn("e0Qlt", mapping["missing_frame_references"])
        self.assertTrue((run_dir / "00-source-pack.md").exists())
        self.assertTrue((run_dir / "03-feature-ui-map.md").exists())

        doctor = run_doctor(Workspace(root))
        self.assertEqual(doctor["health"], "fail")

    def test_feature_ui_map_ignores_generic_frame_prose(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "docs").mkdir()
            (root / "pencil").mkdir()
            (root / "docs" / "architecture.md").write_text(
                "\n".join(
                    [
                        "# Architecture",
                        "",
                        "- `frame_inventory.py`: Pencil `.pen` frame extraction.",
                        "- `g2.py`: Pencil-first design gate backed by `event_tree` and `g2_contract`.",
                        "- UI Mapping Gate: UI-bearing work needs an explicit frame map or `NO_UI`.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "pencil" / "app.pen").write_text(
                json.dumps(
                    {
                        "id": "doc",
                        "type": "frame",
                        "name": "App",
                        "children": [
                            {"id": "abc12", "type": "frame", "name": "Dashboard", "children": []}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = start_run(Workspace(root), "Generic frame prose")
            mapping = json.loads((Path(result["run_dir"]) / "feature-ui-map.json").read_text(encoding="utf-8"))
            self.assertEqual(mapping["status"], "needs_explicit_mapping")
            self.assertEqual(mapping["missing_frame_references"], {})

    def test_start_run_passes_with_valid_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pencil").mkdir()
            (root / "plan").mkdir()
            (root / "pencil" / "app.pen").write_text(
                json.dumps(
                    {
                        "id": "doc",
                        "type": "frame",
                        "name": "App",
                        "children": [
                            {"id": "abc12", "type": "frame", "name": "Dashboard", "children": []}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "plan" / "features.md").write_text(
                "Dashboard UI uses Pencil frame `abc12`.\n",
                encoding="utf-8",
            )

            result = start_run(Workspace(root), "Build dashboard")
            mapping = json.loads((Path(result["run_dir"]) / "feature-ui-map.json").read_text(encoding="utf-8"))
            self.assertEqual(mapping["status"], "ok")
            self.assertIn("abc12", mapping["references"])

            doctor = run_doctor(Workspace(root))
            self.assertEqual(doctor["health"], "pass")

    def test_lifecycle_transitions(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        start_run(Workspace(root), "Lifecycle test")

        paused = set_lifecycle(Workspace(root), "paused", "paused_by_test")
        self.assertEqual(paused["project_lifecycle"], "paused")
        self.assertEqual(paused["mode"], "active")

        ended = set_lifecycle(Workspace(root), "ended", "ended_by_test")
        self.assertEqual(ended["project_lifecycle"], "ended")
        self.assertEqual(ended["mode"], "inactive")

    def test_reset_moves_state_to_backup(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "Reset test")

        result = reset_workspace(ws, confirm=True)
        self.assertTrue(result["backup"])
        self.assertTrue(Path(result["backup"]).exists())
        self.assertFalse((root / ".superteam_codex").exists())

    def test_mode_contains_source_pack_summary(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        start_run(Workspace(root), "Mode summary test")

        mode = load_mode(Workspace(root))
        self.assertIsNotNone(mode)
        assert mode is not None
        self.assertEqual(mode["source_pack"]["pencil_frame_count"], 3)
        self.assertEqual(mode["source_pack"]["feature_ui_map_status"], "blocked_missing_frames")
        self.assertIn("event_tree", mode)
        self.assertNotIn("g1_events", mode)

    def test_g1_events_advance_one_by_one_and_approve(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "G1 state machine test")

        self.assertEqual(g1_status(ws)["active_event"], "G1.START")
        answers = [
            "Build a store management system.",
            "Owners and store managers will use it.",
            "Reports, reconciliation, and operations analysis.",
            "UI is required and Pencil is the design source.",
            "Persist stores, staff, daily reports, and account data.",
            "Need Excel import and enterprise WeChat notifications.",
            "Use the existing local Windows development environment.",
        ]
        for index, answer in enumerate(answers, start=1):
            result = record_g1_answer(ws, answer)
            expected = "G1.SUMMARY" if index == 7 else f"G1.Q{index + 1}"
            self.assertEqual(result["next_event"], expected)

        summary = complete_g1_summary(ws)
        self.assertEqual(summary["next_event"], "G1.APPROVAL")
        approval = approve_g1(ws, note="user approved G1")
        self.assertEqual(approval["event"], "G1.COMPLETE")

        status = g1_status(ws)
        self.assertTrue(status["complete"])
        self.assertIsNone(status["active_event"])
        text = (Path(status["project_definition"])).read_text(encoding="utf-8")
        self.assertIn("G1.Q4", text)
        self.assertIn("approved_by: user", text)

    def test_cannot_leave_g1_before_user_approval(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "G1 gate test")

        with self.assertRaises(StateError):
            set_stage(ws, "g2", "ready_for_design")

    def test_g1_hook_trace_exposes_spawn_and_inspector(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ws = Workspace(root)
            start_run(ws, "G1 hook trace test")

            result = run_g1_hook_trace_until_user_gate(ws)
            self.assertEqual(result["active_event"], "G1.Q1")
            self.assertEqual(
                result["trace_hooks"],
                ["G1.START.enter", "G1.START.next", "G1.Q1.enter", "G1.Q1.hold"],
            )
            self.assertEqual(result["orchestrator"]["spawn_decision"], "none")
            self.assertEqual(result["inspector"]["status"], "not_required")

            answers = [
                "Build a Quest game platform.",
                "Store staff use it.",
                "Login and game library.",
                "Needs UI, use Pencil.",
                "Device and game records.",
                "Quest devices and package files.",
                "Windows local environment.",
            ]
            for answer in answers[:-1]:
                result = apply_g1_hook_trace_signal(ws, "answer", answer)
                self.assertTrue(str(result["active_event"]).startswith("G1.Q"))
                self.assertEqual(result["orchestrator"]["spawn_decision"], "none")

            result = apply_g1_hook_trace_signal(ws, "answer", answers[-1])
            self.assertEqual(result["active_event"], "G1.SUMMARY")
            self.assertIn("G1.SUMMARY.spawn_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["spawn_decision"], "required")
            self.assertEqual(result["orchestrator"]["spawn_status"], "pending")
            self.assertEqual(result["orchestrator"]["expected_agent"], "prd-writer")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "prd-writer")
            summary_spawn_required = next(item for item in result["trace"] if item["hook"] == "G1.SUMMARY.spawn_required")
            self.assert_agent_contract(summary_spawn_required, "prd-writer")
            self.assertEqual(result["inspector"]["status"], "not_required")

            result = apply_g1_hook_trace_signal(
                ws,
                "spawn-record",
                "spawned summary writer",
                agent="prd-writer",
                agent_id="agent-prd-writer",
            )
            self.assertIn("G1.SUMMARY.spawn_record", result["trace_hooks"])
            self.assertIn("G1.SUMMARY.wait_result", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["spawn_status"], "waiting_result")
            self.assertEqual(result["orchestrator"]["agent_calls"][-1]["agent_id"], "agent-prd-writer")
            self.assert_agent_contract(result["orchestrator"]["agent_calls"][-1], "prd-writer")

            result = apply_g1_hook_trace_signal(ws, "agent-result", "prd writer completed")
            self.assertEqual(result["active_event"], "G1.SUMMARY")
            self.assertIn("G1.SUMMARY.result_record", result["trace_hooks"])
            self.assertIn("G1.SUMMARY.inspector_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "inspector")
            self.assertIn("send_input", result["orchestrator"]["hook_instruction"])
            self.assertEqual(result["inspector"]["status"], "waiting_for_spawn_record")

            result = apply_g1_hook_trace_signal(
                ws,
                "inspector-spawn-record",
                "spawned inspector",
                agent="inspector",
                agent_id="agent-inspector",
            )
            self.assertIn("G1.SUMMARY.inspector_spawn_record", result["trace_hooks"])
            self.assertIn("G1.SUMMARY.inspector_wait_result", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["spawn_status"], "waiting_result")

            result = apply_g1_hook_trace_signal(ws, "inspector-result", "inspector checked summary", agent="inspector")
            self.assertEqual(result["active_event"], "G1.APPROVAL")
            self.assertIn("G1.SUMMARY.inspector_result_record", result["trace_hooks"])
            self.assertIn("G1.SUMMARY.inspector_check", result["trace_hooks"])
            self.assertIn("G1.APPROVAL.hold", result["trace_hooks"])
            self.assertEqual(result["inspector"]["trace_coverage"]["status"], "pass")

            result = apply_g1_hook_trace_signal(ws, "approve-g1", "approved")
            self.assertFalse(result["complete"])
            self.assertIn("G1.APPROVAL.inspector_required", result["trace_hooks"])
            result = apply_g1_hook_trace_signal(
                ws,
                "inspector-spawn-record",
                "spawned approval inspector",
                agent="inspector",
                agent_id="agent-inspector",
            )
            self.assertIn("G1.APPROVAL.inspector_spawn_record", result["trace_hooks"])
            result = apply_g1_hook_trace_signal(ws, "inspector-result", "inspector checked approval", agent="inspector")
            self.assertTrue(result["complete"])
            self.assertEqual(result["active_global_event"], "G2")
            self.assertIn("G1.APPROVAL.inspector_check", result["trace_hooks"])
            self.assertIn("G1.COMPLETE.next", result["trace_hooks"])

    def test_can_leave_g1_after_user_approval(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "G1 approve gate test")
        for answer in [
            "Build the project.",
            "Managers use it.",
            "Core features.",
            "No UI needed.",
            "No data persistence needed.",
            "No external systems.",
            "No specified stack.",
        ]:
            record_g1_answer(ws, answer)
        complete_g1_summary(ws)
        approve_g1(ws)

        mode = set_stage(ws, "g2", "ready_for_design")
        self.assertEqual(mode["stage"], "g2")

    def test_g2_pencil_first_event_tree_reaches_g3_with_valid_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pencil").mkdir()
            (root / "plan").mkdir()
            (root / "pencil" / "app.pen").write_text(
                json.dumps(
                    {
                        "id": "doc",
                        "type": "frame",
                        "name": "App",
                        "children": [
                            {"id": "abc12", "type": "frame", "name": "Dashboard", "children": []}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "plan" / "features.md").write_text(
                "Dashboard UI uses Pencil frame `abc12`.\n",
                encoding="utf-8",
            )
            ws = Workspace(root)
            start_run(ws, "Build dashboard")
            for answer in [
                "Build a dashboard.",
                "Admins use it.",
                "Dashboard feature.",
                "Needs UI, use Pencil.",
                "No persistent data.",
                "No external integration.",
                "Use existing stack.",
            ]:
                record_g1_answer(ws, answer)
            complete_g1_summary(ws)
            approval_g1 = approve_g1(ws)

            self.assertEqual(approval_g1["next_global_event"], "G2")
            self.assertEqual(g2_status(ws)["active_event"], "G2.START")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.READ_G1_DEFINITION")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.CHECK_UI_REQUIREMENT")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.DRAFT_UI_DESIGN_PLAN")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.APPROVE_UI_DESIGN_PLAN")
            self.assertEqual(g2_status(ws)["contract"]["ui_plan"], ["Dashboard feature"])
            hooks = [item["hook"] for item in g2_status(ws)["hook_trace"]]
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.enter", hooks)
            with self.assertRaises(StateError):
                advance_g2(ws)
            self.assertEqual(approve_g2_plan(ws, note="UI design plan approved")["next_event"], "G2.APPROVE_UI_DESIGN_PLAN")
            self.assertEqual(self.complete_g2_inspector(ws)["active_event"], "G2.DESIGN_PENCIL_STEPS")
            hooks = [item["hook"] for item in g2_status(ws)["hook_trace"]]
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.record", hooks)
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.inspector_spawn_record", hooks)
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.inspector_check", hooks)
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.next", hooks)
            hooks = [item["hook"] for item in g2_status(ws)["hook_trace"]]
            self.assertIn("G2.DESIGN_PENCIL_STEPS.enter", hooks)
            with self.assertRaises(StateError):
                advance_g2(ws)
            apply_g2_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn designer for Pencil design",
                agent="designer",
                agent_id="agent-designer",
            )
            self.assertEqual(
                record_g2_design_step(ws, "S1 and S2 Pencil frames completed", complete=True)["next_event"],
                "G2.DESIGN_PENCIL_STEPS",
            )
            self.assertEqual(self.complete_g2_inspector(ws)["active_event"], "G2.REVIEW_SOURCE_PACK")
            hooks = [item["hook"] for item in g2_status(ws)["hook_trace"]]
            self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.record", hooks)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.inspector_spawn_record", hooks)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.inspector_check", hooks)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.next", hooks)
            self.assertEqual(advance_g2(ws)["next_event"], "G2.EXTRACT_PENCIL_FRAMES")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.MAP_FEATURE_TO_PENCIL_FRAME")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.CHECK_FEATURE_UI_MAP")
            run_dir = Path(load_mode(ws)["run_dir"])
            self.write_reference_screenshots(run_dir, ["abc12"])
            self.assertEqual(advance_g2(ws)["next_event"], "G2.MAP_PENCIL_TO_CODE_TARGETS")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.EXTRACT_LAYOUT_SPEC")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.EXTRACT_DESIGN_TOKENS")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.MAP_INTERACTION_STATES")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.WRITE_VISUAL_ACCEPTANCE")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.CHECK_UI_IMPLEMENTATION_CONTRACT")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.WRITE_PENCIL_CONTRACT_MAP")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.CHECK_PENCIL_CONTRACT_MAP")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.DRAFT_DESIGN_CONTRACT")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.DELIVER_PENCIL_DESIGN")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.WRITE_DESIGN_ARTIFACT")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.READINESS_CHECK")
            self.assertEqual(advance_g2(ws)["next_event"], "G2.USER_APPROVAL")
            approval = approve_g2(ws, note="G2 approved")

            self.assertEqual(approval["event"], "G2.COMPLETE")
            self.assertEqual(approval["next_global_event"], "G3")
            mode = load_mode(ws)
            self.assertEqual(mode["stage"], "g3")
            text = Path(approval["design"]).read_text(encoding="utf-8")
            self.assertIn("UI authority: Pencil", text)
            self.assertIn("abc12", text)
            self.assertIn("S1 and S2 Pencil frames completed", text)

    def test_g2_blocks_ui_project_when_feature_ui_map_is_not_ok(self) -> None:
        temp, root = self.copy_fixture("sms_minimal")
        self.addCleanup(temp.cleanup)
        ws = Workspace(root)
        start_run(ws, "G2 blocked mapping test")
        for answer in [
            "Build SMS.",
            "Admins use it.",
            "Store management features.",
            "Needs UI, use Pencil.",
            "Store data.",
            "Excel import.",
            "Existing stack.",
        ]:
            record_g1_answer(ws, answer)
        complete_g1_summary(ws)
        approve_g1(ws)

        advance_g2(ws)  # START
        advance_g2(ws)  # READ_G1_DEFINITION
        advance_g2(ws)  # CHECK_UI_REQUIREMENT
        advance_g2(ws)  # DRAFT_UI_DESIGN_PLAN
        self.approve_g2_plan_with_inspector(ws, note="UI design plan approved")
        self.complete_g2_design_step_with_inspector(ws, "Pencil design attempted")
        advance_g2(ws)  # REFRESH_SOURCE_PACK
        advance_g2(ws)  # REVIEW_SOURCE_PACK
        advance_g2(ws)  # EXTRACT_PENCIL_FRAMES
        with self.assertRaises(StateError):
            advance_g2(ws)

        status = g2_status(ws)
        self.assertEqual(status["active_event"], "G2.CHECK_FEATURE_UI_MAP")

    def test_g2_design_steps_must_cover_each_plan_item_before_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pencil").mkdir()
            ws = Workspace(root)
            start_run(ws, "G2 design step gate test")
            for answer in [
                "Build a Quest game platform.",
                "Store staff use it.",
                "Login, game library.",
                "Needs UI, use Pencil.",
                "Game and device records.",
                "Quest devices and package files.",
                "Windows local environment.",
            ]:
                record_g1_answer(ws, answer)
            complete_g1_summary(ws)
            approve_g1(ws)

            advance_g2(ws)  # START
            advance_g2(ws)  # READ_G1_DEFINITION
            advance_g2(ws)  # CHECK_UI_REQUIREMENT
            advance_g2(ws)  # DRAFT_UI_DESIGN_PLAN
            self.approve_g2_plan_with_inspector(ws, note="plan approved")
            mode = load_mode(ws)
            assert mode is not None
            by_id = {item["id"]: item for item in mode["event_tree"]}
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEMS"]["status"], "active")
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEM_001"]["title"], "Login")
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEM_001"]["status"], "active")
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEM_002"]["title"], "game library")
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEM_002"]["status"], "pending")
            apply_g2_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn designer for Pencil design",
                agent="designer",
                agent_id="agent-designer",
            )

            with self.assertRaises(StateError):
                record_g2_design_step(ws, "Login screen done", complete=True)

            status = g2_status(ws)
            self.assertEqual(status["active_event"], "G2.DESIGN_PENCIL_STEPS")
            self.assertEqual(len(status["contract"]["pencil_design"]["steps"]), 0)

            record_g2_design_step(ws, "Login screen done")
            mode = load_mode(ws)
            assert mode is not None
            by_id = {item["id"]: item for item in mode["event_tree"]}
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEM_001"]["status"], "done")
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEM_002"]["status"], "active")
            hooks = [item["hook"] for item in g2_status(ws)["hook_trace"]]
            self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.record", hooks)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.next", hooks)
            result = record_g2_design_step(ws, "Game library screen done", complete=True)
            self.assertEqual(result["next_event"], "G2.DESIGN_PENCIL_STEPS")
            self.assertEqual(self.complete_g2_inspector(ws)["active_event"], "G2.REVIEW_SOURCE_PACK")
            mode = load_mode(ws)
            assert mode is not None
            by_id = {item["id"]: item for item in mode["event_tree"]}
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEMS"]["status"], "done")
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEM_001"]["status"], "done")
            self.assertEqual(by_id["G2.DESIGN_PENCIL_STEPS.ITEM_002"]["status"], "done")
            hooks = [item["hook"] for item in g2_status(ws)["hook_trace"]]
            self.assertIn("G2.DESIGN_PENCIL_STEPS.item2.record", hooks)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.record", hooks)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.next", hooks)

    def test_g2_ui_plan_uses_designer_agent_result_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ws = Workspace(root)
            start_run(ws, "G2 agent plan source test")
            for answer in [
                "Build an employee roster.",
                "Store manager and shareholders use it.",
                "Manager creates, edits, deletes roster; shareholders query roster.",
                "Needs UI, use Pencil, only 2 UI screens.",
                "Employee roster data.",
                "No external integration.",
                "React + Vite + TypeScript + Ant Design + Node.js + Prisma + SQLite.",
            ]:
                record_g1_answer(ws, answer)
            complete_g1_summary(ws)
            approve_g1(ws)

            run_g2_hook_trace_until_user_gate(ws)
            apply_g2_hook_trace_signal(
                ws,
                "spawn-record",
                "spawned designer",
                agent="designer",
                agent_id="agent-designer",
            )
            result = apply_g2_hook_trace_signal(
                ws,
                "agent-result",
                'UI_PLAN_JSON: ["S1 Login", "S2 Employee roster"]',
                agent="designer",
            )

            self.assertEqual(result["ui_plan"], ["S1 Login", "S2 Employee roster"])

    def test_g2_creates_valid_pencil_document_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ws = Workspace(root)
            start_run(ws, "G2 Pencil schema test")
            for answer in [
                "Build an employee roster.",
                "Store manager and shareholders use it.",
                "Manager creates, edits, deletes roster; shareholders query roster.",
                "Needs UI, use Pencil, only 2 UI screens.",
                "Employee roster data.",
                "No external integration.",
                "React + Vite + TypeScript + Ant Design + Node.js + Prisma + SQLite.",
            ]:
                record_g1_answer(ws, answer)
            complete_g1_summary(ws)
            approve_g1(ws)
            run_g2_hook_trace_until_user_gate(ws)
            apply_g2_hook_trace_signal(
                ws,
                "spawn-record",
                "spawned designer",
                agent="designer",
                agent_id="agent-designer",
            )
            apply_g2_hook_trace_signal(
                ws,
                "agent-result",
                "S1 Login\nS2 Employee roster",
                agent="designer",
            )
            self.complete_g2_inspector(ws)
            approve_g2_plan(ws, note="plan approved")
            result = self.complete_g2_inspector(ws)

            mode = load_mode(ws)
            assert mode is not None
            pencil_path = Path(mode["g2_contract"]["ui"]["pencil_project"])
            document = json.loads(pencil_path.read_text(encoding="utf-8"))
            self.assertEqual(result["active_event"], "G2.DESIGN_PENCIL_STEPS")
            self.assertEqual(document["version"], "2.11")
            self.assertEqual(document["children"], [])
            self.assertNotIn("type", document)

    def test_g2_hook_trace_flow_runs_auto_nodes_and_stops_at_user_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ws = Workspace(root)
            start_run(ws, "G2 hook trace flow test")
            for answer in [
                "Build a Quest game platform.",
                "Store staff use it.",
                "Login, game library.",
                "Needs UI, use Pencil.",
                "Game and device records.",
                "Quest devices and package files.",
                "Windows local environment.",
            ]:
                record_g1_answer(ws, answer)
            complete_g1_summary(ws)
            approve_g1(ws)

            result = run_g2_hook_trace_until_user_gate(ws)
            self.assertEqual(result["active_event"], "G2.DRAFT_UI_DESIGN_PLAN")
            self.assertEqual(
                result["trace_hooks"],
                [
                    "G2.START.enter",
                    "G2.START.record",
                    "G2.START.next",
                    "G2.READ_G1_DEFINITION.enter",
                    "G2.READ_G1_DEFINITION.record",
                    "G2.READ_G1_DEFINITION.next",
                    "G2.CHECK_UI_REQUIREMENT.enter",
                    "G2.CHECK_UI_REQUIREMENT.record",
                    "G2.CHECK_UI_REQUIREMENT.next",
                    "G2.DRAFT_UI_DESIGN_PLAN.enter",
                    "G2.DRAFT_UI_DESIGN_PLAN.spawn_required",
                ],
            )
            self.assertEqual(result["orchestrator"]["spawn_decision"], "required")
            self.assertEqual(result["orchestrator"]["spawn_status"], "pending")
            self.assertEqual(result["orchestrator"]["expected_agent"], "designer")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "designer")
            g2_spawn_required = next(item for item in result["trace"] if item["hook"] == "G2.DRAFT_UI_DESIGN_PLAN.spawn_required")
            self.assert_agent_contract(g2_spawn_required, "designer")
            self.assertEqual(result["inspector"]["status"], "not_required")

            result = apply_g2_hook_trace_signal(
                ws,
                "spawn-record",
                "spawned designer",
                agent="designer",
                agent_id="agent-designer",
            )
            self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.spawn_record", result["trace_hooks"])
            self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.wait_result", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["spawn_status"], "waiting_result")
            self.assertEqual(result["orchestrator"]["agent_calls"][-1]["agent_id"], "agent-designer")
            self.assert_agent_contract(result["orchestrator"]["agent_calls"][-1], "designer")

            result = apply_g2_hook_trace_signal(ws, "agent-result", "UI plan drafted", agent="designer")
            self.assertEqual(result["active_event"], "G2.DRAFT_UI_DESIGN_PLAN")
            self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.result_record", result["trace_hooks"])
            self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.inspector_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "inspector")

            result = apply_g2_hook_trace_signal(
                ws,
                "inspector-spawn-record",
                "spawned design-plan inspector",
                agent="inspector",
                agent_id="agent-inspector",
            )
            self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.inspector_spawn_record", result["trace_hooks"])
            result = apply_g2_hook_trace_signal(ws, "inspector-result", "inspector checked UI plan", agent="inspector")
            self.assertEqual(result["active_event"], "G2.APPROVE_UI_DESIGN_PLAN")
            self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.inspector_result_record", result["trace_hooks"])
            self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.inspector_check", result["trace_hooks"])
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.hold", result["trace_hooks"])

            result = apply_g2_hook_trace_signal(ws, "approve-plan", "閫氳繃")
            self.assertEqual(result["active_event"], "G2.APPROVE_UI_DESIGN_PLAN")
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.inspector_required", result["trace_hooks"])
            result = apply_g2_hook_trace_signal(
                ws,
                "inspector-spawn-record",
                "spawned approve-plan inspector",
                agent="inspector",
                agent_id="agent-inspector",
            )
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.inspector_spawn_record", result["trace_hooks"])
            result = apply_g2_hook_trace_signal(ws, "inspector-result", "inspector checked approve plan", agent="inspector")
            self.assertEqual(result["active_event"], "G2.DESIGN_PENCIL_STEPS")
            mode = load_mode(ws)
            assert mode is not None
            event_ids = [item["id"] for item in mode["event_tree"]]
            self.assertIn("G2.DESIGN_PENCIL_STEPS", event_ids)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.ITEMS", event_ids)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.ITEM_001", event_ids)
            self.assertIn("G2.DESIGN_PENCIL_STEPS.ITEM_002", event_ids)
            self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.next", result["trace_hooks"])
            self.assertIn("G2.CREATE_PENCIL_PROJECT.enter", result["trace_hooks"])
            self.assertIn("G2.OPEN_PENCIL.next", result["trace_hooks"])
            self.assertIn("G2.DESIGN_PENCIL_STEPS.enter", result["trace_hooks"])
            self.assertIn("G2.DESIGN_PENCIL_STEPS.spawn_required", result["trace_hooks"])

            result = apply_g2_hook_trace_signal(
                ws,
                "spawn-record",
                "spawned designer for Pencil design",
                agent="designer",
                agent_id="agent-designer",
            )
            self.assertIn("G2.DESIGN_PENCIL_STEPS.spawn_record", result["trace_hooks"])
            self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.enter", result["trace_hooks"])
            self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.hold", result["trace_hooks"])

            result = apply_g2_hook_trace_signal(ws, "design-step", "S1 login page")
            self.assertEqual(result["active_event"], "G2.DESIGN_PENCIL_STEPS")
            self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.record", result["trace_hooks"])
            result = apply_g2_hook_trace_signal(ws, "design-step", "S2 game library", complete=True)
            self.assertEqual(result["active_event"], "G2.DESIGN_PENCIL_STEPS")
            self.assertIn("G2.DESIGN_PENCIL_STEPS.inspector_required", result["trace_hooks"])
            result = apply_g2_hook_trace_signal(
                ws,
                "inspector-spawn-record",
                "spawned design-step inspector",
                agent="inspector",
                agent_id="agent-inspector",
            )
            self.assertIn("G2.DESIGN_PENCIL_STEPS.inspector_spawn_record", result["trace_hooks"])
            result = apply_g2_hook_trace_signal(ws, "inspector-result", "inspector checked design steps", agent="inspector")
            self.assertEqual(result["active_event"], "G2.REVIEW_SOURCE_PACK")
            self.assertIn("G2.DESIGN_PENCIL_STEPS.inspector_check", result["trace_hooks"])
            self.assertIn("G2.REVIEW_SOURCE_PACK.spawn_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "researcher")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "researcher")

    def test_g3_hook_trace_maps_pencil_frames_to_code_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pencil").mkdir()
            (root / "plan").mkdir()
            (root / "pencil" / "app.pen").write_text(
                json.dumps(
                    {
                        "id": "doc",
                        "version": "2.11",
                        "children": [
                            {"id": "s1_login", "type": "frame", "name": "S1 Login", "children": []},
                            {"id": "s2_roster", "type": "frame", "name": "S2 Employee roster", "children": []},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "plan" / "features.md").write_text(
                "Login UI uses Pencil frame `s1_login`.\nRoster UI uses Pencil frame `s2_roster`.\n",
                encoding="utf-8",
            )
            ws = Workspace(root)
            start_run(ws, "Build employee roster")
            for answer in [
                "Build an employee roster.",
                "Store manager and shareholders use it.",
                "Employee roster feature.",
                "Needs UI, use Pencil.",
                "Employee roster data.",
                "No external integration.",
                "React + Vite + TypeScript + Ant Design + Node.js + Prisma + SQLite.",
            ]:
                record_g1_answer(ws, answer)
            complete_g1_summary(ws)
            approve_g1(ws)

            advance_g2(ws)  # START
            advance_g2(ws)  # READ_G1_DEFINITION
            advance_g2(ws)  # CHECK_UI_REQUIREMENT
            advance_g2(ws)  # DRAFT_UI_DESIGN_PLAN
            self.approve_g2_plan_with_inspector(ws, note="plan approved")
            self.complete_g2_design_step_with_inspector(ws, "S1 and S2 Pencil frames completed")
            run_dir = Path(load_mode(ws)["run_dir"])
            self.write_reference_screenshots(run_dir, ["s1_login", "s2_roster"])
            for _ in range(16):
                advance_g2(ws)
            approve_g2(ws, note="G2 approved")

            result = run_g3_hook_trace_until_user_gate(ws)
            self.assertEqual(result["active_event"], "G3.SCAN_IMPLEMENTATION_SURFACE")
            self.assertIn("G3.SCAN_IMPLEMENTATION_SURFACE.spawn_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "architect")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "architect")

            result = self.complete_g3_spawned_event(
                ws,
                "architect",
                "agent-architect",
                "PASS: implementation surface scanned",
            )
            architect_call = next(item for item in result["orchestrator"]["agent_calls"] if item["event"] == "G3.SCAN_IMPLEMENTATION_SURFACE" and item["role"] == "architect")
            self.assert_agent_contract(architect_call, "architect")
            self.assertEqual(result["active_event"], "G3.DRAFT_EXECUTION_PLAN")
            self.assertIn("G3.CHECK_UI_CODE_MAP.record", result["trace_hooks"])
            self.assertIn("G3.MATERIALIZE_WORK_ITEMS.record", result["trace_hooks"])
            ui_code_map = json.loads((Path(load_mode(ws)["run_dir"]) / "ui-code-map.json").read_text(encoding="utf-8"))
            self.assertEqual(ui_code_map["status"], "ok")
            self.assertEqual({item["frame_id"] for item in ui_code_map["mappings"]}, {"s1_login", "s2_roster"})
            self.assertEqual(json.loads((run_dir / "ui-layout-spec.json").read_text(encoding="utf-8"))["status"], "ok")
            self.assertEqual(json.loads((run_dir / "design-tokens.json").read_text(encoding="utf-8"))["status"], "ok")
            self.assertEqual(json.loads((run_dir / "interaction-state-map.json").read_text(encoding="utf-8"))["status"], "ok")
            self.assertEqual(json.loads((run_dir / "visual-acceptance.json").read_text(encoding="utf-8"))["status"], "ok")
            pencil_contract_map = json.loads((run_dir / "pencil-contract-map.json").read_text(encoding="utf-8"))
            self.assertEqual(pencil_contract_map["status"], "ok")
            self.assertEqual(set(pencil_contract_map["contracts"].keys()), {"s1_login", "s2_roster"})
            for frame_id, contract in pencil_contract_map["contracts"].items():
                self.assertEqual(contract["contract_ref"], f"pencil-contract-map.json#contracts.{frame_id}")
                self.assertEqual(contract["pencil"]["frame_id"], frame_id)
                self.assertEqual(contract["pencil"]["reference_screenshot"], f"evidence/g2/reference/{frame_id}-reference.png")
                self.assertTrue(contract["implementation"]["code_targets"])
                self.assertIn("visual-acceptance.json", " ".join(contract["hard_constraints"]["required_before_implementation"]))
                self.assertIn(f"evidence/g6/{frame_id}-implementation.png", contract["hard_constraints"]["required_evidence"])
                self.assertIn("evidence/g5/visual-review-report.json", contract["hard_constraints"]["required_evidence"])
                self.assertIn("evidence/g6/visual-acceptance-report.json", contract["hard_constraints"]["required_evidence"])

            apply_g3_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn planner",
                agent="planner",
                agent_id="agent-planner",
            )
            apply_g3_hook_trace_signal(
                ws,
                "agent-result",
                "FAIL: plan lacks scaffold, UI/API targets, and Node verification commands",
                agent="planner",
            )
            result = self.complete_g3_inspector(ws, "Inspector PASS: planner failure is valid")
            self.assertEqual(result["active_event"], "G3.DRAFT_EXECUTION_PLAN")
            self.assertIn("G3.DRAFT_EXECUTION_PLAN.repair_required", result["trace_hooks"])
            self.assertIn("G3.DRAFT_EXECUTION_PLAN.repair_materialized", result["trace_hooks"])
            implementation_plan = json.loads((run_dir / "implementation-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(implementation_plan["status"], "ok")
            repaired_kinds = {item["kind"] for item in implementation_plan["work_items"]}
            self.assertIn("scaffold", repaired_kinds)
            repaired_commands = {command for item in implementation_plan["work_items"] for command in item["verification_commands"]}
            self.assertIn("npm run typecheck", repaired_commands)
            self.assertNotIn("python -m compileall .", repaired_commands)

            result = self.complete_g3_spawned_event(
                ws,
                "planner",
                "agent-planner",
                "PASS: implementation plan drafted",
            )
            self.assertEqual(result["active_event"], "G3.USER_APPROVAL")
            self.assertIn("G3.USER_APPROVAL.hold", result["trace_hooks"])
            implementation_plan = json.loads((run_dir / "implementation-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(implementation_plan["status"], "ok")
            kinds = {item["kind"] for item in implementation_plan["work_items"]}
            self.assertIn("scaffold", kinds)
            self.assertIn("data_api", kinds)
            ui_items = [item for item in implementation_plan["work_items"] if item["kind"] == "ui"]
            self.assertTrue(ui_items)
            self.assertTrue(all(item.get("spec_refs") for item in ui_items))
            self.assertEqual({item["frame_ids"][0] for item in ui_items}, set(pencil_contract_map["contracts"].keys()))
            self.assertTrue(all(item["contract_ref"] == item["spec_refs"].get("pencil_contract") for item in ui_items))
            self.assertTrue(all(item["contract_ref"].startswith("pencil-contract-map.json#contracts.") for item in ui_items))
            self.assertTrue(all(item["evidence_refs"]["reference_screenshot"].startswith("evidence/g2/reference/") for item in ui_items))
            self.assertTrue(all(item["evidence_refs"]["implementation_screenshot"].startswith("evidence/g6/") for item in ui_items))
            self.assertTrue(all("pencil-contract-map.json" in " ".join(item["acceptance_checks"]) for item in ui_items))
            self.assertTrue(all("visual-acceptance.json" in " ".join(item["acceptance_checks"]) for item in ui_items))
            commands = {command for item in implementation_plan["work_items"] for command in item["verification_commands"]}
            self.assertIn("npm run typecheck", commands)
            self.assertIn("npm run build", commands)
            self.assertIn("npx prisma validate", commands)
            self.assertNotIn("python -m compileall .", commands)
            self.assertTrue((run_dir / "04-plan.md").read_text(encoding="utf-8").startswith("# G3 Execution Plan"))

            result = apply_g3_hook_trace_signal(ws, "approve-g3", "G3 approved")
            self.assertIn("G3.USER_APPROVAL.inspector_required", result["trace_hooks"])
            result = self.complete_g3_inspector(ws, "inspector checked G3 approval")
            self.assertTrue(result["complete"])
            mode = load_mode(ws)
            self.assertEqual(mode["stage"], "execute")
            self.assertEqual(mode["g3_approval"]["status"], "approved")
            self.assertEqual(mode["orchestrator"]["active_event"], "G4.START")
            self.assertEqual(mode["orchestrator"]["spawn_status"], "not_required")
            self.assertIsNone(mode["orchestrator"]["expected_agent"])
            self.assertEqual(mode["inspector"]["active_event"], "G4.START")
            self.assertFalse(mode["inspector"]["checkpoint_required"])

            result = run_g4_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G4.SPAWN_EXECUTOR")
            self.assertIn("G4.SPAWN_EXECUTOR.spawn_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "executor")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "executor")

            result = apply_g4_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn executor",
                agent="executor",
                agent_id="agent-executor",
            )
            self.assertIn("G4.SPAWN_EXECUTOR.spawn_record", result["trace_hooks"])
            self.assert_agent_contract(result["orchestrator"]["agent_calls"][-1], "executor")
            with self.assertRaises(StateError) as blocked_result:
                apply_g4_hook_trace_signal(ws, "agent-result", "executor tried to finish before TDD", agent="executor")
            self.assertIn("G4 TDD gate blocked", str(blocked_result.exception))
            first_work_item = code_changing_work_items(implementation_plan)[0]["id"]
            with self.assertRaises(StateError) as blocked_green:
                apply_g4_hook_trace_signal(
                    ws,
                    "tdd-green",
                    "green cannot happen before red",
                    work_item_id=first_work_item,
                    command="npm run test:api",
                    passed=1,
                    failed=0,
                )
            self.assertIn("RED_LOCKED", str(blocked_green.exception))
            self.complete_g4_tdd_cycle(ws, implementation_plan)
            mode = load_mode(ws)
            assert mode is not None
            trace_hooks = [item.get("hook") for item in mode.get("hook_trace", []) if isinstance(item, dict)]
            self.assertIn("G4.UI_GUIDANCE.WI-003", trace_hooks)
            self.assertIn("G4.UI_GUIDANCE.WI-004", trace_hooks)
            ui_item = mode["g4_contract"]["tdd"]["items"]["WI-003"]
            saved_guidance = ui_item.pop("ui_guidance")
            save_mode(ws, mode)
            with self.assertRaises(StateError) as blocked_ui_guidance:
                apply_g4_hook_trace_signal(ws, "agent-result", "executor tried to finish without UI guidance", agent="executor")
            self.assertIn("G4 UI guidance gate blocked", str(blocked_ui_guidance.exception))
            mode = load_mode(ws)
            assert mode is not None
            mode["g4_contract"]["tdd"]["items"]["WI-003"]["ui_guidance"] = saved_guidance
            save_mode(ws, mode)
            self.write_implementation_screenshots(run_dir, ["s1_login", "s2_roster"])
            execution_artifact = run_dir / "05-execution.md"
            execution_artifact.write_text(
                self.executor_artifact_text("agent-executor", implementation_plan),
                encoding="utf-8",
            )
            result = apply_g4_hook_trace_signal(
                ws,
                "agent-result",
                "PASS: executor completed approved work items",
                agent="executor",
            )
            self.assertEqual(result["active_event"], "G4.READINESS_CHECK")
            self.assertIn("G4.READINESS_CHECK.inspector_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "inspector")
            self.assertTrue((run_dir / "05-execution.md").exists())
            execution_text = execution_artifact.read_text(encoding="utf-8")
            self.assertIn("Status: implementation_complete", execution_text)
            self.assertIn("executor-authored evidence", execution_text)
            self.assertNotIn("Status: recorded", execution_text)

            result = apply_g4_hook_trace_signal(
                ws,
                "inspector-spawn-record",
                "spawn inspector",
                agent="inspector",
                agent_id="agent-inspector",
            )
            self.assertIn("G4.READINESS_CHECK.inspector_spawn_record", result["trace_hooks"])
            result = apply_g4_hook_trace_signal(ws, "inspector-result", "inspector checked G4 readiness", agent="inspector")
            self.assertTrue(result["complete"])
            mode = load_mode(ws)
            self.assertEqual(mode["stage"], "review")
            self.assertEqual(mode["orchestrator"]["active_event"], "G5.START")

            result = run_g5_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G5.SPAWN_REVIEWER")
            self.assertIn("G5.REVIEW_GUIDANCE.inputs", result["trace_hooks"])
            self.assertIn("G5.UI_REVIEW_GUIDANCE", result["trace_hooks"])
            self.assertIn("G5.UI_REVIEW_GUIDANCE.s1_login", result["trace_hooks"])
            self.assertIn("G5.UI_REVIEW_GUIDANCE.s2_roster", result["trace_hooks"])
            self.assertIn("G5.SPAWN_REVIEWER.spawn_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "reviewer")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "reviewer")

            result = apply_g5_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn reviewer",
                agent="reviewer",
                agent_id="agent-reviewer",
            )
            self.assertIn("G5.SPAWN_REVIEWER.spawn_record", result["trace_hooks"])
            self.assert_agent_contract(result["orchestrator"]["agent_calls"][-1], "reviewer")
            review_artifact = run_dir / "06-review.md"
            review_artifact.write_text(
                self.blocked_review_artifact_text("agent-reviewer", load_mode(ws)["active_task_slug"]),
                encoding="utf-8",
            )
            self.write_review_contract(run_dir, verdict="BLOCK", ui_status="block")
            result = apply_g5_hook_trace_signal(
                ws,
                "agent-result",
                "BLOCK: reviewer found UI mismatch before verification",
                agent="reviewer",
            )
            self.assertEqual(result["active_event"], "G5.UI_QUALITY_REVIEW")
            self.assertIn("G5.RECORD_REVIEW_EVIDENCE.record", result["trace_hooks"])
            self.assertIn("G5.UI_QUALITY_REVIEW.designer_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "designer")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "designer")

            result = apply_g5_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn designer for UI quality review",
                agent="designer",
                agent_id="agent-designer",
            )
            self.assertIn("G5.UI_QUALITY_REVIEW.spawn_record", result["trace_hooks"])
            self.assert_agent_contract(result["orchestrator"]["agent_calls"][-1], "designer")
            result = apply_g5_hook_trace_signal(
                ws,
                "agent-result",
                "BLOCK: UI fidelity failed against Pencil and G3/G4 contracts",
                agent="designer",
            )
            self.assertFalse(result["complete"])
            self.assertEqual(result["active_global_event"], "G4")
            self.assertEqual(result["active_event"], "G4.START")
            self.assertIn("G5.RETURN_TO_G4.iteration_1", result["trace_hooks"])
            mode = load_mode(ws)
            self.assertEqual(mode["stage"], "execute")
            self.assertEqual(mode["repair_loop"]["active_iteration"], 1)
            self.assertEqual(mode["g4_contract"]["repair_context"]["source_event"], "G5.CHECK_REVIEW_GATE")
            self.assertEqual(mode["g4_contract"]["repair_context"]["verdict"], "BLOCK")
            archive_dir = Path(mode["repair_loop"]["history"][-1]["archive"]["path"])
            self.assertTrue((archive_dir / "05-execution.md").exists())
            self.assertTrue((archive_dir / "06-review.md").exists())
            self.assertTrue((archive_dir / "review-contract.json").exists())

            result = run_g4_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G4.SPAWN_EXECUTOR")
            self.assertIn("G4.REPAIR_GUIDANCE.iteration_1", result["trace_hooks"])
            result = apply_g4_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn executor for G5 block repair",
                agent="executor",
                agent_id="agent-executor",
            )
            self.assertIn("G4.SPAWN_EXECUTOR.spawn_record", result["trace_hooks"])
            self.complete_g4_tdd_cycle(ws, implementation_plan)
            execution_artifact.write_text(
                self.executor_artifact_text("agent-executor", implementation_plan),
                encoding="utf-8",
            )
            result = apply_g4_hook_trace_signal(
                ws,
                "agent-result",
                "PASS: executor repaired G5 review blockers",
                agent="executor",
            )
            self.assertEqual(result["active_event"], "G4.READINESS_CHECK")
            apply_g4_hook_trace_signal(
                ws,
                "inspector-spawn-record",
                "spawn inspector for G5 block repair",
                agent="inspector",
                agent_id="agent-inspector",
            )
            result = apply_g4_hook_trace_signal(ws, "inspector-result", "inspector checked G5 block repair", agent="inspector")
            self.assertTrue(result["complete"])
            self.assertEqual(load_mode(ws)["stage"], "review")

            result = run_g5_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G5.SPAWN_REVIEWER")
            self.assertIn("G5.REVIEW_GUIDANCE.inputs", result["trace_hooks"])
            apply_g5_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn reviewer after G5 block repair",
                agent="reviewer",
                agent_id="agent-reviewer",
            )
            review_artifact.write_text(
                self.review_artifact_text("agent-reviewer", load_mode(ws)["active_task_slug"]),
                encoding="utf-8",
            )
            self.write_review_contract(run_dir)
            result = apply_g5_hook_trace_signal(
                ws,
                "agent-result",
                "CLEAR_WITH_CONCERNS: reviewer accepted G5 block repair",
                agent="reviewer",
            )
            self.assertEqual(result["active_event"], "G5.UI_QUALITY_REVIEW")
            apply_g5_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn designer after G5 block repair",
                agent="designer",
                agent_id="agent-designer",
            )
            self.write_visual_report(run_dir, "evidence/g5/visual-review-report.json", ["s1_login", "s2_roster"])
            result = apply_g5_hook_trace_signal(
                ws,
                "agent-result",
                "PASS: UI fidelity checked after G5 block repair",
                agent="designer",
            )
            self.assertTrue(result["complete"])
            mode = load_mode(ws)
            self.assertEqual(mode["stage"], "verify")
            self.assertEqual(mode["g5_contract"]["status"], "done")
            self.assertEqual(mode["g5_contract"]["verdict"], "CLEAR_WITH_CONCERNS")
            self.assertEqual(mode["orchestrator"]["active_event"], "G6.START")

            result = run_g6_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G6.SPAWN_VERIFIER")
            apply_g6_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn verifier for failing verification",
                agent="verifier",
                agent_id="agent-verifier",
            )
            verification_artifact = run_dir / "07-verification.md"
            verification_artifact.write_text(
                self.failed_verification_artifact_text("agent-verifier", load_mode(ws)["active_task_slug"]),
                encoding="utf-8",
            )
            self.write_verification_contract(run_dir, verdict="FAIL", confidence="low", ui_status="fail")
            result = apply_g6_hook_trace_signal(
                ws,
                "agent-result",
                "FAIL: verifier found UI mismatch",
                agent="verifier",
            )
            self.assertFalse(result["complete"])
            self.assertEqual(result["active_global_event"], "G4")
            self.assertEqual(result["active_event"], "G4.START")
            mode = load_mode(ws)
            self.assertEqual(mode["stage"], "execute")
            self.assertEqual(mode["repair_loop"]["active_iteration"], 2)
            self.assertEqual(mode["g4_contract"]["repair_context"]["verdict"], "FAIL")
            archive_dir = Path(mode["repair_loop"]["history"][-1]["archive"]["path"])
            self.assertTrue((archive_dir / "05-execution.md").exists())
            self.assertTrue((archive_dir / "06-review.md").exists())
            self.assertTrue((archive_dir / "07-verification.md").exists())
            self.assertTrue((archive_dir / "review-contract.json").exists())
            self.assertTrue((archive_dir / "verification-contract.json").exists())

            result = run_g4_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G4.SPAWN_EXECUTOR")
            self.assertIn("G4.REPAIR_GUIDANCE.iteration_2", result["trace_hooks"])
            self.assertIn("G4.SPAWN_EXECUTOR.spawn_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "executor")
            result = apply_g4_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn executor for repair",
                agent="executor",
                agent_id="agent-executor",
            )
            self.assertIn("G4.SPAWN_EXECUTOR.spawn_record", result["trace_hooks"])
            self.complete_g4_tdd_cycle(ws, implementation_plan)
            execution_artifact.write_text(
                self.executor_artifact_text("agent-executor", implementation_plan),
                encoding="utf-8",
            )
            result = apply_g4_hook_trace_signal(
                ws,
                "agent-result",
                "PASS: executor repaired failed G6 verification items",
                agent="executor",
            )
            self.assertEqual(result["active_event"], "G4.READINESS_CHECK")
            apply_g4_hook_trace_signal(
                ws,
                "inspector-spawn-record",
                "spawn repair inspector",
                agent="inspector",
                agent_id="agent-inspector",
            )
            result = apply_g4_hook_trace_signal(ws, "inspector-result", "inspector checked repair readiness", agent="inspector")
            self.assertTrue(result["complete"])
            self.assertEqual(load_mode(ws)["stage"], "review")

            result = run_g5_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G5.SPAWN_REVIEWER")
            self.assertIn("G5.REVIEW_GUIDANCE.inputs", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "reviewer")
            apply_g5_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn reviewer for repair",
                agent="reviewer",
                agent_id="agent-reviewer",
            )
            review_artifact.write_text(
                self.review_artifact_text("agent-reviewer", load_mode(ws)["active_task_slug"]),
                encoding="utf-8",
            )
            self.write_review_contract(run_dir)
            result = apply_g5_hook_trace_signal(
                ws,
                "agent-result",
                "CLEAR_WITH_CONCERNS: reviewer checked repaired delivery",
                agent="reviewer",
            )
            self.assertEqual(result["active_event"], "G5.UI_QUALITY_REVIEW")
            apply_g5_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn designer for repaired UI quality review",
                agent="designer",
                agent_id="agent-designer",
            )
            self.write_visual_report(run_dir, "evidence/g5/visual-review-report.json", ["s1_login", "s2_roster"])
            result = apply_g5_hook_trace_signal(
                ws,
                "agent-result",
                "PASS: repaired UI fidelity checked against Pencil and G3/G4 contracts",
                agent="designer",
            )
            self.assertTrue(result["complete"])
            self.assertEqual(load_mode(ws)["stage"], "verify")

            result = run_g6_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G6.SPAWN_VERIFIER")
            self.assertIn("G6.VERIFICATION_GUIDANCE.inputs", result["trace_hooks"])
            self.assertIn("G6.TEST_EVIDENCE_GUIDANCE", result["trace_hooks"])
            self.assertIn("G6.UI_VERIFICATION_GUIDANCE", result["trace_hooks"])
            self.assertIn("G6.UI_VERIFICATION_GUIDANCE.s1_login", result["trace_hooks"])
            self.assertIn("G6.UI_VERIFICATION_GUIDANCE.s2_roster", result["trace_hooks"])
            self.assertIn("G6.SPAWN_VERIFIER.spawn_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "verifier")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "verifier")

            result = apply_g6_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn verifier",
                agent="verifier",
                agent_id="agent-verifier",
            )
            self.assertIn("G6.SPAWN_VERIFIER.spawn_record", result["trace_hooks"])
            self.assert_agent_contract(result["orchestrator"]["agent_calls"][-1], "verifier")
            verification_artifact = run_dir / "07-verification.md"
            self.write_visual_report(run_dir, "evidence/g6/visual-acceptance-report.json", ["s1_login", "s2_roster"])
            verification_artifact.write_text(
                self.verification_artifact_text("agent-verifier", load_mode(ws)["active_task_slug"]),
                encoding="utf-8",
            )
            self.write_verification_contract(run_dir)
            result = apply_g6_hook_trace_signal(
                ws,
                "agent-result",
                "PASS: verifier completed fresh evidence checks",
                agent="verifier",
            )
            self.assertTrue(result["complete"])
            mode = load_mode(ws)
            self.assertEqual(mode["stage"], "finish")
            self.assertEqual(mode["g6_contract"]["status"], "done")
            self.assertEqual(mode["g6_contract"]["verdict"], "PASS")
            self.assertEqual(mode["g6_contract"]["delivery_confidence"], "high")
            self.assertEqual(mode["orchestrator"]["active_event"], "G7.START")

            result = run_g7_hook_trace_until_stage_gate(ws)
            self.assertEqual(result["active_event"], "G7.SPAWN_INSPECTOR")
            self.assertIn("G7.FINISH_INPUTS_GUIDANCE", result["trace_hooks"])
            self.assertIn("G7.NO_PRODUCT_CODE_CHANGE_GUIDANCE", result["trace_hooks"])
            self.assertIn("G7.INSPECTOR_GUIDANCE", result["trace_hooks"])
            self.assertIn("G7.SPAWN_INSPECTOR.spawn_required", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "inspector")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "inspector")

            result = apply_g7_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn inspector for G7",
                agent="inspector",
                agent_id="agent-inspector",
            )
            self.assertIn("G7.SPAWN_INSPECTOR.spawn_record", result["trace_hooks"])
            self.assert_agent_contract(result["orchestrator"]["agent_calls"][-1], "inspector")
            inspector_report = inspector_report_path(load_mode(ws))
            inspector_report.parent.mkdir(parents=True, exist_ok=True)
            inspector_report.write_text(
                self.inspector_report_text("agent-inspector", load_mode(ws)["active_task_slug"]),
                encoding="utf-8",
            )
            self.write_inspector_audit(run_dir)
            result = apply_g7_hook_trace_signal(
                ws,
                "agent-result",
                "PASS: inspector completed process audit",
                agent="inspector",
            )
            self.assertEqual(result["active_event"], "G7.SPAWN_WRITER")
            self.assertIn("G7.RECORD_INSPECTOR_REPORT.record", result["trace_hooks"])
            self.assertIn("G7.FINISH_GUIDANCE", result["trace_hooks"])
            self.assertEqual(result["orchestrator"]["expected_agent"], "writer")
            self.assert_agent_contract(result["orchestrator"]["expected_agent_definition"], "writer")

            result = apply_g7_hook_trace_signal(
                ws,
                "spawn-record",
                "spawn writer for finish",
                agent="writer",
                agent_id="agent-writer",
            )
            self.assertIn("G7.SPAWN_WRITER.spawn_record", result["trace_hooks"])
            self.assert_agent_contract(result["orchestrator"]["agent_calls"][-1], "writer")
            (run_dir / "08-finish.md").write_text(
                self.finish_artifact_text("agent-writer", load_mode(ws)["active_task_slug"]),
                encoding="utf-8",
            )
            (run_dir / "retrospective.md").write_text(self.retrospective_text(), encoding="utf-8")
            self.write_finish_contract(run_dir)
            result = apply_g7_hook_trace_signal(
                ws,
                "agent-result",
                "writer completed finish and retrospective",
                agent="writer",
            )
            self.assertTrue(result["complete"])
            mode = load_mode(ws)
            self.assertEqual(mode["stage"], "finish")
            self.assertEqual(mode["project_lifecycle"], "complete")
            self.assertEqual(mode["mode"], "inactive")
            self.assertEqual(mode["g7_contract"]["status"], "done")
            self.assertEqual(mode["orchestrator"]["active_event"], "G7.COMPLETE")
            self.assertTrue((run_dir / "08-finish.md").exists())
            self.assertTrue((run_dir / "retrospective.md").exists())
            self.assertTrue((run_dir / "finish-contract.json").exists())
            self.assertTrue((run_dir / "inspector-audit.json").exists())
            self.assertTrue(inspector_report.exists())


if __name__ == "__main__":
    unittest.main()
