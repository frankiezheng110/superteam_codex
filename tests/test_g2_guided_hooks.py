from __future__ import annotations

import unittest

from superteam_codex.runtime.g2_guided_hooks import DONE, DOING, run_g2_guided_simulation


class G2GuidedHookSimulationTests(unittest.TestCase):
    def test_g2_plan_design_completeness_and_delivery_reaches_g3(self) -> None:
        result = run_g2_guided_simulation()

        self.assertTrue(result["ok"])
        self.assertEqual(result["active_node"], "G3.START")
        tree = result["tree"]
        self.assertEqual(tree["G2.COMPLETE"]["status"], DONE)
        self.assertEqual(tree["G3.START"]["status"], DOING)
        self.assertEqual(tree["G2.CHECK_FEATURE_UI_MAP"]["payload"]["missing_features"], [])

        deliverables = tree["G2.DELIVER_PENCIL_DESIGN"]["payload"]["deliverables"]
        self.assertIn("Pencil .pen 原稿", deliverables)
        self.assertIn("feature-ui-map.json", deliverables)

        hooks = [item["hook"] for item in result["trace"]]
        self.assertIn("G2.START.record", hooks)
        self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.spawn_required", hooks)
        self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.spawn_record", hooks)
        self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.inspector_spawn_record", hooks)
        self.assertIn("G2.DRAFT_UI_DESIGN_PLAN.inspector_check", hooks)
        self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.hold", hooks)
        self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.inspector_required", hooks)
        self.assertIn("G2.APPROVE_UI_DESIGN_PLAN.inspector_spawn_record", hooks)
        self.assertIn("G2.DESIGN_PENCIL_STEPS.enter", hooks)
        self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.enter", hooks)
        self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.hold", hooks)
        self.assertIn("G2.DESIGN_PENCIL_STEPS.item1.record", hooks)
        self.assertIn("G2.DESIGN_PENCIL_STEPS.record", hooks)
        self.assertIn("G2.DESIGN_PENCIL_STEPS.inspector_check", hooks)
        self.assertIn("G2.REVIEW_SOURCE_PACK.spawn_required", hooks)
        self.assertIn("G2.DRAFT_DESIGN_CONTRACT.spawn_required", hooks)
        self.assertIn("G2.WRITE_DESIGN_ARTIFACT.spawn_required", hooks)
        self.assertIn("G2.WRITE_DESIGN_ARTIFACT.inspector_check", hooks)
        self.assertIn("G2.USER_APPROVAL.hold", hooks)
        self.assertIn("G2.USER_APPROVAL.inspector_check", hooks)
        self.assertEqual(result["orchestrator"]["agent_calls"][-1]["role"], "inspector")
        self.assertEqual(result["inspector"]["agent_id"], "simulated-inspector-user-approval")
        self.assertLess(
            hooks.index("G2.APPROVE_UI_DESIGN_PLAN.hold"),
            hooks.index("G2.APPROVE_UI_DESIGN_PLAN.record"),
        )
        self.assertLess(
            hooks.index("G2.DESIGN_PENCIL_STEPS.item1.hold"),
            hooks.index("G2.DESIGN_PENCIL_STEPS.item1.record"),
        )

        instructions = [item["instruction"] for item in result["trace"]]
        self.assertIn("agent 生成 UI 设计计划", instructions)
        self.assertIn("agent 请求确认 UI 设计计划", instructions)
        self.assertIn("用户设计步骤 1: 设计登录页", instructions)
        self.assertIn("agent 检查 UI 完整性", instructions)
        self.assertIn("agent 交付 Pencil 设计稿", instructions)
        self.assertIn("agent 写 G2 交付文件", instructions)

        plan_approval = instructions.index("agent 记录 UI 设计计划确认")
        first_design_step = instructions.index("用户设计步骤 1: 设计登录页")
        completeness = instructions.index("agent 检查 UI 完整性")
        delivery = instructions.index("agent 交付 Pencil 设计稿")
        handoff = instructions.index("agent 写 G2 交付文件")
        self.assertLess(plan_approval, first_design_step)
        self.assertLess(completeness, delivery)
        self.assertLess(delivery, handoff)


if __name__ == "__main__":
    unittest.main()
