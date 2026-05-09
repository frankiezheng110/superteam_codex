from __future__ import annotations

import unittest

from superteam_codex.runtime.g1_guided_hooks import DONE, DOING, run_g1_guided_simulation


class G1GuidedHookSimulationTests(unittest.TestCase):
    def test_project_start_to_g1_complete_uses_end_signal_before_next_question(self) -> None:
        result = run_g1_guided_simulation(task="做一个门店报账系统")

        self.assertTrue(result["ok"])
        self.assertEqual(result["active_node"], "G2.START")
        tree = result["tree"]
        self.assertEqual(tree["G1.COMPLETE"]["status"], DONE)
        self.assertEqual(tree["G2.START"]["status"], DOING)

        trace = result["trace"]
        hooks = [item["hook"] for item in trace]
        self.assertIn("G1.SUMMARY.spawn_required", hooks)
        self.assertIn("G1.SUMMARY.spawn_record", hooks)
        self.assertIn("G1.SUMMARY.inspector_required", hooks)
        self.assertIn("G1.SUMMARY.inspector_spawn_record", hooks)
        self.assertIn("G1.SUMMARY.inspector_check", hooks)
        self.assertIn("G1.APPROVAL.inspector_required", hooks)
        self.assertIn("G1.APPROVAL.inspector_spawn_record", hooks)
        self.assertIn("G1.APPROVAL.inspector_check", hooks)
        self.assertIsNone(result["orchestrator"]["expected_agent"])
        self.assertEqual(result["orchestrator"]["agent_calls"][-1]["role"], "inspector")
        self.assertEqual(result["inspector"]["agent_id"], "simulated-inspector-approval")
        self.assertEqual(result["inspector"]["trace_coverage"]["status"], "pass")

        instructions = [item["instruction"] for item in trace]
        self.assertIn("创建项目树", instructions)
        self.assertIn("agent 问 Q1", instructions)
        self.assertIn("agent 保持 Q1", instructions)
        self.assertIn("agent 记录 Q1", instructions)
        self.assertIn("推进到 G1.Q2", instructions)
        self.assertIn("agent 问 Q2", instructions)

        q1_hold = instructions.index("agent 保持 Q1")
        q1_record = instructions.index("agent 记录 Q1")
        q2_ask = instructions.index("agent 问 Q2")
        self.assertLess(q1_hold, q1_record)
        self.assertLess(q1_record, q2_ask)


if __name__ == "__main__":
    unittest.main()
