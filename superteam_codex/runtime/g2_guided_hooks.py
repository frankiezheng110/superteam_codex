from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .event_tree import G2_EVENT_IDS


TODO = "未完成"
DOING = "完成中"
DONE = "已完成"

DEFAULT_G1_FEATURES = [
    "游戏安装",
    "游戏启动",
    "游戏关闭",
    "保持 Quest3 到电视机投屏",
    "服务器游戏管理",
]

DEFAULT_UI_PLAN = [
    "设计登录页",
    "设计游戏平台主界面",
    "设计设备绑定页",
    "设计游戏安装页",
    "设计游戏启动、关闭、投屏状态页",
    "设计服务器游戏管理页",
]

TITLES = {
    "G2.START": "启动 G2",
    "G2.READ_G1_DEFINITION": "读取 G1 交付文件",
    "G2.CHECK_UI_REQUIREMENT": "确认是否 UI 项目",
    "G2.DRAFT_UI_DESIGN_PLAN": "生成 UI 设计计划",
    "G2.APPROVE_UI_DESIGN_PLAN": "用户确认 UI 设计计划",
    "G2.CREATE_PENCIL_PROJECT": "创建或确认 Pencil 项目文件",
    "G2.OPEN_PENCIL": "打开 Pencil",
    "G2.DESIGN_PENCIL_STEPS": "按计划强交互设计 Pencil UI",
    "G2.REFRESH_SOURCE_PACK": "刷新 source pack",
    "G2.REVIEW_SOURCE_PACK": "审查 source pack",
    "G2.EXTRACT_PENCIL_FRAMES": "提取 Pencil frames",
    "G2.MAP_FEATURE_TO_PENCIL_FRAME": "映射 G1 功能到 Pencil frame",
    "G2.CHECK_FEATURE_UI_MAP": "校验 feature-ui-map",
    "G2.DRAFT_DESIGN_CONTRACT": "生成 G2 设计合同",
    "G2.DELIVER_PENCIL_DESIGN": "交付 Pencil 设计稿",
    "G2.WRITE_DESIGN_ARTIFACT": "生成 G2 交付文件",
    "G2.READINESS_CHECK": "G2 完成前校验",
    "G2.USER_APPROVAL": "用户确认 G2",
    "G2.COMPLETE": "关闭 G2",
}

INSPECTOR_AGENT = "inspector"
G2_PENCIL_DESIGN_AGENT = "designer"
G2_SPAWN_POLICIES: dict[str, dict[str, str]] = {
    "G2.DRAFT_UI_DESIGN_PLAN": {
        "agent": "designer",
        "scope": "draft the G2 UI design plan from G1",
    },
    "G2.REVIEW_SOURCE_PACK": {
        "agent": "researcher",
        "scope": "review source pack before contract drafting",
    },
    "G2.DRAFT_DESIGN_CONTRACT": {
        "agent": "architect",
        "scope": "draft the G2 design contract",
    },
    "G2.WRITE_DESIGN_ARTIFACT": {
        "agent": "architect",
        "scope": "write the derived G2 design artifact",
    },
}


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
        "payload": {},
    }


def create_g2_tree() -> dict[str, Any]:
    tree = {
        "G2": _node("G2", "G2 Pencil 设计与源审查", DOING, "G3.START"),
        "G3.START": _node("G3.START", "启动 G3", TODO),
    }
    for index, event_id in enumerate(G2_EVENT_IDS):
        next_event = G2_EVENT_IDS[index + 1] if index + 1 < len(G2_EVENT_IDS) else "G3.START"
        tree[event_id] = _node(event_id, TITLES[event_id], DOING if index == 0 else TODO, next_event)
    return tree


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


def _advance(trace: list[HookStep], tree: dict[str, Any], event_id: str, instruction: str) -> str:
    _step(trace, f"{event_id}.enter", f"{event_id} = 完成中", tree, event_id, instruction)
    _step(trace, f"{event_id}.record", f"{event_id} = recorded", tree, event_id, "agent records G2 auto event")
    _set_done(tree, event_id)
    next_event = str(tree[event_id]["next"])
    _step(trace, f"{event_id}.next", f"{event_id} = 已完成", tree, event_id, f"推进到 {next_event}")
    _set_doing(tree, next_event)
    return next_event


def _inspector_gate(trace: list[HookStep], tree: dict[str, Any], event_id: str, agent_id: str) -> None:
    _step(
        trace,
        f"{event_id}.inspector_required",
        f"expected_agent={INSPECTOR_AGENT}",
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


def _advance_spawned(trace: list[HookStep], tree: dict[str, Any], event_id: str, instruction: str) -> str:
    policy = G2_SPAWN_POLICIES[event_id]
    agent = policy["agent"]
    _step(trace, f"{event_id}.enter", f"{event_id} = 完成中", tree, event_id, instruction)
    _step(
        trace,
        f"{event_id}.spawn_required",
        f"expected_agent={agent}",
        tree,
        event_id,
        f"OR spawn {agent}; main session must not complete {event_id} directly",
    )
    _step(
        trace,
        f"{event_id}.spawn_record",
        f"agent_id=simulated-{agent}",
        tree,
        event_id,
        f"record {agent} spawn",
    )
    _step(trace, f"{event_id}.wait_result", "waiting for agent result", tree, event_id, f"wait for {agent} result")
    _step(trace, f"{event_id}.result_record", f"{agent} completed", tree, event_id, f"record {agent} result")
    _inspector_gate(trace, tree, event_id, f"simulated-inspector-{event_id.lower().replace('.', '-')}")
    _set_done(tree, event_id)
    next_event = str(tree[event_id]["next"])
    _step(trace, f"{event_id}.next", f"{event_id} = 已完成", tree, event_id, f"推进到 {next_event}")
    _set_doing(tree, next_event)
    return next_event


def _feature_frame_map(features: list[str]) -> dict[str, str]:
    return {feature: f"frame-{index:02d}" for index, feature in enumerate(features, start=1)}


def run_g2_guided_simulation(
    features: list[str] | None = None,
    ui_plan: list[str] | None = None,
    plan_approval: str = "确认 UI 设计计划",
    design_done_signal: str = "设计完成",
    approval: str = "确认 G2",
) -> dict[str, Any]:
    feature_items = features or DEFAULT_G1_FEATURES
    plan_items = ui_plan or DEFAULT_UI_PLAN
    tree = create_g2_tree()
    trace: list[HookStep] = []

    _advance(trace, tree, "G2.START", "agent 启动 G2")

    tree["G2.READ_G1_DEFINITION"]["payload"]["features"] = feature_items
    _advance(trace, tree, "G2.READ_G1_DEFINITION", "agent 读取 G1 交付文件")

    tree["G2.CHECK_UI_REQUIREMENT"]["payload"]["ui_required"] = True
    _advance(trace, tree, "G2.CHECK_UI_REQUIREMENT", "agent 确认这是 UI 项目")

    tree["G2.DRAFT_UI_DESIGN_PLAN"]["payload"]["ui_plan"] = plan_items
    _advance_spawned(trace, tree, "G2.DRAFT_UI_DESIGN_PLAN", "agent 生成 UI 设计计划")

    _step(
        trace,
        "G2.APPROVE_UI_DESIGN_PLAN.enter",
        "G2.APPROVE_UI_DESIGN_PLAN = 完成中",
        tree,
        "G2.APPROVE_UI_DESIGN_PLAN",
        "agent 请求确认 UI 设计计划",
    )
    _step(
        trace,
        "G2.APPROVE_UI_DESIGN_PLAN.hold",
        "waiting for user approval",
        tree,
        "G2.APPROVE_UI_DESIGN_PLAN",
        "agent holds at UI design plan approval",
    )
    _step(
        trace,
        "G2.APPROVE_UI_DESIGN_PLAN.record",
        f"用户确认：{plan_approval}",
        tree,
        "G2.APPROVE_UI_DESIGN_PLAN",
        "agent 记录 UI 设计计划确认",
    )
    _inspector_gate(trace, tree, "G2.APPROVE_UI_DESIGN_PLAN", "simulated-inspector-approve-ui-design-plan")
    _set_done(tree, "G2.APPROVE_UI_DESIGN_PLAN")
    _step(
        trace,
        "G2.APPROVE_UI_DESIGN_PLAN.next",
        "G2.APPROVE_UI_DESIGN_PLAN = 已完成",
        tree,
        "G2.APPROVE_UI_DESIGN_PLAN",
        "推进到 G2.CREATE_PENCIL_PROJECT",
    )
    _set_doing(tree, "G2.CREATE_PENCIL_PROJECT")

    _advance(trace, tree, "G2.CREATE_PENCIL_PROJECT", "agent 创建或确认项目专属 Pencil 文件")
    _advance(trace, tree, "G2.OPEN_PENCIL", "agent 打开 Pencil")

    _step(
        trace,
        "G2.DESIGN_PENCIL_STEPS.enter",
        "G2.DESIGN_PENCIL_STEPS = active",
        tree,
        "G2.DESIGN_PENCIL_STEPS",
        "agent enters Pencil strong-interaction design",
    )
    _step(
        trace,
        "G2.DESIGN_PENCIL_STEPS.spawn_required",
        f"expected_agent={G2_PENCIL_DESIGN_AGENT}",
        tree,
        "G2.DESIGN_PENCIL_STEPS",
        "OR spawn designer before user-steered Pencil design",
    )
    _step(
        trace,
        "G2.DESIGN_PENCIL_STEPS.spawn_record",
        "agent_id=simulated-designer-pencil",
        tree,
        "G2.DESIGN_PENCIL_STEPS",
        "record designer spawn",
    )
    for index, item in enumerate(plan_items, start=1):
        _step(
            trace,
            f"G2.DESIGN_PENCIL_STEPS.item{index}.enter",
            f"设计步骤 {index} = 完成中",
            tree,
            "G2.DESIGN_PENCIL_STEPS",
            f"用户设计步骤 {index}: {item}",
        )
        _step(
            trace,
            f"G2.DESIGN_PENCIL_STEPS.item{index}.hold",
            "waiting for user-steered Pencil design",
            tree,
            "G2.DESIGN_PENCIL_STEPS",
            f"agent holds at Pencil design item {index}",
        )
        _step(
            trace,
            f"G2.DESIGN_PENCIL_STEPS.item{index}.record",
            f"用户结束信号：{design_done_signal}",
            tree,
            "G2.DESIGN_PENCIL_STEPS",
            f"agent 记录设计步骤 {index}",
        )
        if index < len(plan_items):
            _step(
                trace,
                f"G2.DESIGN_PENCIL_STEPS.item{index}.next",
                f"item{index} = done",
                tree,
                "G2.DESIGN_PENCIL_STEPS",
                f"advance to Pencil design item {index + 1}",
            )
    tree["G2.DESIGN_PENCIL_STEPS"]["payload"]["completed_steps"] = plan_items
    _step(
        trace,
        "G2.DESIGN_PENCIL_STEPS.record",
        f"user design-done signal: {design_done_signal}",
        tree,
        "G2.DESIGN_PENCIL_STEPS",
        "agent records Pencil design completion",
    )
    _inspector_gate(trace, tree, "G2.DESIGN_PENCIL_STEPS", "simulated-inspector-design-pencil-steps")
    _set_done(tree, "G2.DESIGN_PENCIL_STEPS")
    _step(
        trace,
        "G2.DESIGN_PENCIL_STEPS.next",
        "G2.DESIGN_PENCIL_STEPS = 已完成",
        tree,
        "G2.DESIGN_PENCIL_STEPS",
        "推进到 G2.REFRESH_SOURCE_PACK",
    )
    _set_doing(tree, "G2.REFRESH_SOURCE_PACK")

    _advance(trace, tree, "G2.REFRESH_SOURCE_PACK", "agent 刷新 source pack 和 Pencil frame inventory")
    _advance_spawned(trace, tree, "G2.REVIEW_SOURCE_PACK", "agent 审查 source pack")

    frames = _feature_frame_map(feature_items)
    tree["G2.EXTRACT_PENCIL_FRAMES"]["payload"]["frames"] = list(frames.values())
    _advance(trace, tree, "G2.EXTRACT_PENCIL_FRAMES", "agent 提取 Pencil frames")

    tree["G2.MAP_FEATURE_TO_PENCIL_FRAME"]["payload"]["feature_ui_map"] = frames
    _advance(trace, tree, "G2.MAP_FEATURE_TO_PENCIL_FRAME", "agent 映射 G1 功能到 Pencil frame")

    tree["G2.CHECK_FEATURE_UI_MAP"]["payload"]["missing_features"] = []
    _advance(trace, tree, "G2.CHECK_FEATURE_UI_MAP", "agent 检查 UI 完整性")

    _advance_spawned(trace, tree, "G2.DRAFT_DESIGN_CONTRACT", "agent 生成 G2 设计合同")

    tree["G2.DELIVER_PENCIL_DESIGN"]["payload"]["deliverables"] = [
        "Pencil .pen 原稿",
        "frame-inventory.json",
        "feature-ui-map.json",
        "UI frame 清单",
        "G1 功能到 UI frame 映射",
    ]
    _advance(trace, tree, "G2.DELIVER_PENCIL_DESIGN", "agent 交付 Pencil 设计稿")
    _advance_spawned(trace, tree, "G2.WRITE_DESIGN_ARTIFACT", "agent 写 G2 交付文件")
    _advance(trace, tree, "G2.READINESS_CHECK", "agent 执行 G2 完成前校验")

    _step(trace, "G2.USER_APPROVAL.enter", "G2.USER_APPROVAL = 完成中", tree, "G2.USER_APPROVAL", "agent 请求用户确认 G2")
    _step(trace, "G2.USER_APPROVAL.hold", "waiting for user approval", tree, "G2.USER_APPROVAL", "hold at G2 approval")
    _step(trace, "G2.USER_APPROVAL.record", f"用户确认：{approval}", tree, "G2.USER_APPROVAL", "agent 记录 G2 确认")
    _inspector_gate(trace, tree, "G2.USER_APPROVAL", "simulated-inspector-user-approval")
    _set_done(tree, "G2.USER_APPROVAL")
    _step(trace, "G2.USER_APPROVAL.next", "G2.USER_APPROVAL = 已完成", tree, "G2.USER_APPROVAL", "推进到 G2.COMPLETE")
    _set_doing(tree, "G2.COMPLETE")

    _advance(trace, tree, "G2.COMPLETE", "agent 完成 G2")
    _set_done(tree, "G2")

    return {
        "ok": True,
        "active_node": "G3.START",
        "tree": tree,
        "trace": [item.as_dict() for item in trace],
        "orchestrator": {
            "spawn_decision": "completed",
            "expected_agent": None,
            "agent_calls": [
                {
                    "event": event_id,
                    "role": policy["agent"],
                    "agent_id": f"simulated-{policy['agent']}",
                    "status": "completed",
                }
                for event_id, policy in G2_SPAWN_POLICIES.items()
            ]
            + [
                {
                    "event": event_id,
                    "role": INSPECTOR_AGENT,
                    "agent_id": f"simulated-inspector-{event_id.lower().replace('.', '-')}",
                    "status": "completed",
                }
                for event_id in [
                    "G2.DRAFT_UI_DESIGN_PLAN",
                    "G2.REVIEW_SOURCE_PACK",
                    "G2.DRAFT_DESIGN_CONTRACT",
                    "G2.WRITE_DESIGN_ARTIFACT",
                ]
            ]
            + [
                {
                    "event": "G2.DESIGN_PENCIL_STEPS",
                    "role": G2_PENCIL_DESIGN_AGENT,
                    "agent_id": "simulated-designer-pencil",
                    "status": "completed",
                },
                {
                    "event": "G2.APPROVE_UI_DESIGN_PLAN",
                    "role": INSPECTOR_AGENT,
                    "agent_id": "simulated-inspector-approve-ui-design-plan",
                    "status": "completed",
                },
                {
                    "event": "G2.DESIGN_PENCIL_STEPS",
                    "role": INSPECTOR_AGENT,
                    "agent_id": "simulated-inspector-design-pencil-steps",
                    "status": "completed",
                },
                {
                    "event": "G2.USER_APPROVAL",
                    "role": INSPECTOR_AGENT,
                    "agent_id": "simulated-inspector-user-approval",
                    "status": "completed",
                },
            ],
        },
        "inspector": {
            "status": "pass",
            "agent_id": "simulated-inspector-user-approval",
            "checkpoint_required": True,
            "trace_coverage": {"status": "pass", "missing_events": [], "discrepancies": []},
        },
    }
