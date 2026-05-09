from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .event_tree import G1_QUESTIONS


TODO = "未完成"
DOING = "完成中"
DONE = "已完成"

DEFAULT_G1_ANSWERS = [
    "做一个门店报账管理系统。",
    "老板、店长和财务使用。",
    "报账、对账、经营分析和审批。",
    "需要 UI，使用 Pencil。",
    "需要保存门店、员工、日报和报账数据。",
    "需要 Excel 导入和企业微信通知。",
    "使用现有 Windows 本地开发环境。",
]


@dataclass(frozen=True)
class HookStep:
    hook: str
    trigger: str
    node: str
    soft_constraint: str
    instruction: str

    def as_dict(self) -> dict[str, str]:
        return {
            "hook": self.hook,
            "trigger": self.trigger,
            "node": self.node,
            "soft_constraint": self.soft_constraint,
            "instruction": self.instruction,
        }


def _node(event_id: str, title: str, status: str = TODO, next_event: str | None = None) -> dict[str, Any]:
    return {
        "id": event_id,
        "status": status,
        "soft_constraint": title,
        "next": next_event,
        "answer": "",
    }


def create_project_tree(task: str) -> dict[str, Any]:
    questions = []
    for index, (event_id, question) in enumerate(G1_QUESTIONS):
        next_event = G1_QUESTIONS[index + 1][0] if index + 1 < len(G1_QUESTIONS) else "G1.SUMMARY"
        questions.append(_node(event_id, question, next_event=next_event))
    return {
        "PROJECT": _node("PROJECT", task, DOING, "RUN"),
        "RUN": _node("RUN", "本轮 SuperTeam 工作流", TODO, "G1.START"),
        "G1": _node("G1", "G1 项目定义", TODO, "G2.START"),
        "G1.START": _node("G1.START", "启动 G1", TODO, "G1.Q1"),
        **{item["id"]: item for item in questions},
        "G1.SUMMARY": _node("G1.SUMMARY", "汇总项目定义", TODO, "G1.APPROVAL"),
        "G1.APPROVAL": _node("G1.APPROVAL", "用户确认 G1", TODO, "G1.COMPLETE"),
        "G1.COMPLETE": _node("G1.COMPLETE", "关闭 G1", TODO, "G2.START"),
        "G2.START": _node("G2.START", "启动 G2", TODO),
    }


def _set_doing(tree: dict[str, Any], event_id: str) -> None:
    tree[event_id]["status"] = DOING


def _set_done(tree: dict[str, Any], event_id: str) -> None:
    tree[event_id]["status"] = DONE


def _step(
    trace: list[HookStep],
    hook: str,
    trigger: str,
    tree: dict[str, Any],
    node: str,
    instruction: str,
) -> None:
    trace.append(
        HookStep(
            hook=hook,
            trigger=trigger,
            node=node,
            soft_constraint=str(tree[node]["soft_constraint"]),
            instruction=instruction,
        )
    )


def _inspector_gate(trace: list[HookStep], tree: dict[str, Any], event_id: str, agent_id: str) -> None:
    _step(
        trace,
        f"{event_id}.inspector_required",
        "expected_agent=inspector",
        tree,
        event_id,
        "OR must spawn inspector; main session must not impersonate Inspector",
    )
    _step(
        trace,
        f"{event_id}.inspector_spawn_record",
        f"agent_id={agent_id}",
        tree,
        event_id,
        "record inspector spawn",
    )
    _step(
        trace,
        f"{event_id}.inspector_wait_result",
        "waiting for inspector result",
        tree,
        event_id,
        "wait for inspector result",
    )
    _step(
        trace,
        f"{event_id}.inspector_result_record",
        "inspector completed",
        tree,
        event_id,
        "record inspector result",
    )
    _step(
        trace,
        f"{event_id}.inspector_check",
        "inspector trace coverage pass",
        tree,
        event_id,
        "Inspector agent completed trace check",
    )


def run_g1_guided_simulation(
    task: str = "构建一个 SuperTeam Codex 示例项目",
    answers: list[str] | None = None,
    end_signal: str = "下一个",
    approval: str = "确认 G1",
) -> dict[str, Any]:
    answer_items = answers or DEFAULT_G1_ANSWERS
    if len(answer_items) != len(G1_QUESTIONS):
        raise ValueError(f"G1 simulation requires {len(G1_QUESTIONS)} answers")

    tree = create_project_tree(task)
    trace: list[HookStep] = []

    _step(trace, "SUPERTEAM.INVOKE", f"$superteam {task}", tree, "PROJECT", "创建项目树")

    _step(trace, "PROJECT_TREE.CREATED", "项目树已创建", tree, "RUN", "启动 RUN")
    _set_doing(tree, "RUN")

    _step(trace, "RUN.START", "RUN = 完成中", tree, "RUN", "推进到 G1.START")
    _set_doing(tree, "G1")
    _set_doing(tree, "G1.START")

    _step(trace, "G1.START.enter", "G1.START = 完成中", tree, "G1.START", "推进到 G1.Q1")
    _set_done(tree, "G1.START")
    _set_doing(tree, "G1.Q1")

    for index, ((event_id, question), answer) in enumerate(zip(G1_QUESTIONS, answer_items, strict=True), start=1):
        _step(trace, f"{event_id}.enter", f"{event_id} = 完成中", tree, event_id, f"agent 问 Q{index}")
        tree[event_id]["answer"] = answer
        _step(trace, f"{event_id}.hold", "用户回答 + 非结束信号", tree, event_id, f"agent 保持 Q{index}")
        _step(trace, f"{event_id}.record", f"用户结束信号：{end_signal}", tree, event_id, f"agent 记录 Q{index}")
        _set_done(tree, event_id)
        next_event = str(tree[event_id]["next"])
        _step(trace, f"{event_id}.next", f"{event_id} = 已完成", tree, event_id, f"推进到 {next_event}")
        _set_doing(tree, next_event)

    _step(trace, "G1.SUMMARY.enter", "G1.SUMMARY = 完成中", tree, "G1.SUMMARY", "agent 生成 G1 摘要")
    _step(trace, "G1.SUMMARY.spawn_required", "expected_agent=prd-writer", tree, "G1.SUMMARY", "OR spawn prd-writer")
    _step(trace, "G1.SUMMARY.spawn_record", "agent_id=simulated-prd-writer", tree, "G1.SUMMARY", "record prd-writer spawn")
    _step(trace, "G1.SUMMARY.wait_result", "waiting for agent result", tree, "G1.SUMMARY", "wait for prd-writer result")
    _step(trace, "G1.SUMMARY.result_record", "prd-writer completed", tree, "G1.SUMMARY", "record prd-writer result")
    _inspector_gate(trace, tree, "G1.SUMMARY", "simulated-inspector-summary")
    _set_done(tree, "G1.SUMMARY")

    _step(trace, "G1.SUMMARY.next", "G1.SUMMARY = 已完成", tree, "G1.SUMMARY", "推进到 G1.APPROVAL")
    _set_doing(tree, "G1.APPROVAL")

    _step(trace, "G1.APPROVAL.enter", "G1.APPROVAL = 完成中", tree, "G1.APPROVAL", "agent 请求用户确认 G1")
    _step(trace, "G1.APPROVAL.hold", "waiting for user approval", tree, "G1.APPROVAL", "hold at G1 approval")
    _step(trace, "G1.APPROVAL.record", f"用户确认：{approval}", tree, "G1.APPROVAL", "agent 记录 G1 确认")
    _inspector_gate(trace, tree, "G1.APPROVAL", "simulated-inspector-approval")
    _set_done(tree, "G1.APPROVAL")

    _step(trace, "G1.APPROVAL.next", "G1.APPROVAL = 已完成", tree, "G1.APPROVAL", "推进到 G1.COMPLETE")
    _set_doing(tree, "G1.COMPLETE")

    _step(trace, "G1.COMPLETE.enter", "G1.COMPLETE = 完成中", tree, "G1.COMPLETE", "完成 G1")
    _set_done(tree, "G1.COMPLETE")
    _set_done(tree, "G1")

    _step(trace, "G1.COMPLETE.next", "G1.COMPLETE = 已完成", tree, "G1.COMPLETE", "推进到 G2.START")
    _set_doing(tree, "G2.START")

    return {
        "ok": True,
        "task": task,
        "active_node": "G2.START",
        "tree": tree,
        "trace": [item.as_dict() for item in trace],
        "orchestrator": {
            "spawn_decision": "completed",
            "expected_agent": None,
            "agent_calls": [
                {
                    "event": "G1.SUMMARY",
                    "role": "prd-writer",
                    "agent_id": "simulated-prd-writer",
                    "status": "completed",
                },
                {
                    "event": "G1.SUMMARY",
                    "role": "inspector",
                    "agent_id": "simulated-inspector-summary",
                    "status": "completed",
                },
                {
                    "event": "G1.APPROVAL",
                    "role": "inspector",
                    "agent_id": "simulated-inspector-approval",
                    "status": "completed",
                }
            ],
        },
        "inspector": {
            "status": "pass",
            "agent_id": "simulated-inspector-approval",
            "checkpoint_required": True,
            "trace_coverage": {"status": "pass", "missing_events": [], "discrepancies": []},
        },
    }
