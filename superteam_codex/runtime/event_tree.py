from __future__ import annotations

from typing import Any


EVENT_STATUS_VALUES = {"pending", "active", "done", "deferred", "not_applicable", "blocked"}
EVENT_TERMINAL_STATUSES = {"done", "deferred", "not_applicable"}

STAGE_PHASES = [
    ("g1", "G1", "Project definition", "01-project-definition.md"),
    ("g2", "G2", "Pencil design and source review", "02-design.md"),
    ("g3", "G3", "Execution plan", "04-plan.md"),
    ("execute", "G4", "Execution", "05-execution.md"),
    ("review", "G5", "Review", "06-review.md"),
    ("verify", "G6", "Verification", "07-verification.md"),
    ("finish", "G7", "Finish", "08-finish.md"),
]
STAGE_TO_PHASE = {stage: phase for stage, phase, _title, _artifact in STAGE_PHASES}
PHASE_TO_STAGE = {phase: stage for stage, phase, _title, _artifact in STAGE_PHASES}

G1_QUESTIONS = [
    ("G1.Q1", "项目想实现什么？"),
    ("G1.Q2", "谁使用项目？有哪些角色？"),
    ("G1.Q3", "项目具备哪些功能？"),
    ("G1.Q4", "项目是否需要 UI 界面？如果需要，采用什么 UI 工具？"),
    ("G1.Q5", "项目是否需要数据存储？核心数据有哪些？"),
    ("G1.Q6", "项目是否需要接入外部系统或文件？"),
    ("G1.Q7", "项目有什么指定技术栈、现有代码或硬性限制？"),
]

G2_EVENT_IDS = [
    "G2.START",
    "G2.READ_G1_DEFINITION",
    "G2.CHECK_UI_REQUIREMENT",
    "G2.DRAFT_UI_DESIGN_PLAN",
    "G2.APPROVE_UI_DESIGN_PLAN",
    "G2.CREATE_PENCIL_PROJECT",
    "G2.OPEN_PENCIL",
    "G2.DESIGN_PENCIL_STEPS",
    "G2.REFRESH_SOURCE_PACK",
    "G2.REVIEW_SOURCE_PACK",
    "G2.EXTRACT_PENCIL_FRAMES",
    "G2.MAP_FEATURE_TO_PENCIL_FRAME",
    "G2.CHECK_FEATURE_UI_MAP",
    "G2.DRAFT_DESIGN_CONTRACT",
    "G2.DELIVER_PENCIL_DESIGN",
    "G2.WRITE_DESIGN_ARTIFACT",
    "G2.READINESS_CHECK",
    "G2.USER_APPROVAL",
    "G2.COMPLETE",
]

G3_EVENT_IDS = [
    "G3.START",
    "G3.READ_G1_G2_DELIVERABLES",
    "G3.CHECK_G2_APPROVED",
    "G3.LOAD_PENCIL_AUTHORITY",
    "G3.SCAN_IMPLEMENTATION_SURFACE",
    "G3.MAP_PENCIL_TO_CODE_TARGETS",
    "G3.CHECK_UI_CODE_MAP",
    "G3.EXTRACT_LAYOUT_SPEC",
    "G3.EXTRACT_DESIGN_TOKENS",
    "G3.MAP_INTERACTION_STATES",
    "G3.WRITE_VISUAL_ACCEPTANCE",
    "G3.CHECK_UI_IMPLEMENTATION_CONTRACT",
    "G3.MATERIALIZE_WORK_ITEMS",
    "G3.DRAFT_EXECUTION_PLAN",
    "G3.CHECK_EXECUTION_PLAN",
    "G3.WRITE_PLAN_ARTIFACT",
    "G3.READINESS_CHECK",
    "G3.USER_APPROVAL",
    "G3.COMPLETE",
]

G4_EVENT_IDS = [
    "G4.START",
    "G4.LOAD_APPROVED_PLAN",
    "G4.CHECK_G3_APPROVED",
    "G4.SPAWN_EXECUTOR",
    "G4.EXECUTE_WORK_ITEMS",
    "G4.RECORD_EXECUTION_EVIDENCE",
    "G4.OPTIONAL_POLISH",
    "G4.READINESS_CHECK",
    "G4.COMPLETE",
]

G5_EVENT_IDS = [
    "G5.START",
    "G5.LOAD_REVIEW_INPUTS",
    "G5.CHECK_G4_COMPLETE",
    "G5.SPAWN_REVIEWER",
    "G5.RECORD_REVIEW_EVIDENCE",
    "G5.UI_QUALITY_REVIEW",
    "G5.CHECK_REVIEW_GATE",
    "G5.COMPLETE",
]

G6_EVENT_IDS = [
    "G6.START",
    "G6.LOAD_VERIFICATION_INPUTS",
    "G6.CHECK_G5_COMPLETE",
    "G6.SPAWN_VERIFIER",
    "G6.RECORD_VERIFICATION_EVIDENCE",
    "G6.CHECK_VERIFICATION_GATE",
    "G6.COMPLETE",
]

G7_EVENT_IDS = [
    "G7.START",
    "G7.LOAD_FINISH_INPUTS",
    "G7.CHECK_G6_PASS",
    "G7.SPAWN_INSPECTOR",
    "G7.RECORD_INSPECTOR_REPORT",
    "G7.SPAWN_WRITER",
    "G7.WRITE_FINISH_ARTIFACTS",
    "G7.CHECK_FINISH_GATE",
    "G7.COMPLETE",
]


def _node(
    event_id: str,
    *,
    parent: str | None,
    phase: str | None,
    kind: str,
    status: str,
    title: str,
    next_event: str | None = None,
    requires: list[str] | None = None,
    authority: list[str] | None = None,
    artifact: str | None = None,
    hook_policy: str = "",
    requires_answer: bool = False,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "parent": parent,
        "phase": phase,
        "kind": kind,
        "status": status,
        "title": title,
        "requires": requires or [],
        "next": next_event,
        "authority": authority or [],
        "artifact": artifact,
        "hook_policy": hook_policy,
        "requires_answer": requires_answer,
        "answer": "",
        "answer_ref": None,
    }


def _phase_nodes() -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for index, (stage, phase, title, artifact) in enumerate(STAGE_PHASES):
        next_phase = STAGE_PHASES[index + 1][1] if index + 1 < len(STAGE_PHASES) else None
        nodes.append(
            _node(
                phase,
                parent="RUN",
                phase=phase,
                kind="phase",
                status="active" if phase == "G1" else "pending",
                title=title,
                next_event=next_phase,
                artifact=artifact,
                hook_policy="single_active_global_phase",
            )
            | {"stage": stage}
        )
    return nodes


def _g1_nodes() -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = [
        _node(
            "G1.START",
            parent="G1",
            phase="G1",
            kind="start",
            status="active",
            title="启动 G1",
            next_event="G1.Q1",
            authority=["event_tree"],
            artifact="01-project-definition.md",
            hook_policy="enter_g1_before_questions",
        )
    ]
    for index, (event_id, question) in enumerate(G1_QUESTIONS):
        next_event = G1_QUESTIONS[index + 1][0] if index + 1 < len(G1_QUESTIONS) else "G1.SUMMARY"
        nodes.append(
            _node(
                event_id,
                parent="G1",
                phase="G1",
                kind="question",
                status="pending",
                title=question,
                next_event=next_event,
                authority=["user_prompt", "01-project-definition.md"],
                artifact="01-project-definition.md",
                hook_policy="user_answer_required",
                requires_answer=True,
            )
        )
    nodes.extend(
        [
            _node(
                "G1.SUMMARY",
                parent="G1",
                phase="G1",
                kind="summary",
                status="pending",
                title="汇总项目定义",
                next_event="G1.APPROVAL",
                authority=["event_tree", "01-project-definition.md"],
                artifact="01-project-definition.md",
                hook_policy="all_g1_questions_terminal",
            ),
            _node(
                "G1.APPROVAL",
                parent="G1",
                phase="G1",
                kind="approval",
                status="pending",
                title="用户确认 G1",
                next_event="G1.COMPLETE",
                authority=["user_prompt"],
                artifact="01-project-definition.md",
                hook_policy="user_only",
            ),
            _node(
                "G1.COMPLETE",
                parent="G1",
                phase="G1",
                kind="complete",
                status="pending",
                title="G1 关闭",
                authority=["event_tree"],
                artifact="01-project-definition.md",
                hook_policy="advance_to_g2",
            ),
        ]
    )
    return nodes


def _g2_nodes() -> list[dict[str, Any]]:
    titles = {
        "G2.START": "启动 G2",
        "G2.READ_G1_DEFINITION": "读取 G1 项目定义",
        "G2.CHECK_UI_REQUIREMENT": "确认是否 UI 项目",
        "G2.DRAFT_UI_DESIGN_PLAN": "生成 UI 设计计划",
        "G2.APPROVE_UI_DESIGN_PLAN": "用户确认 UI 设计计划",
        "G2.CREATE_PENCIL_PROJECT": "创建或确认 Pencil 项目文件",
        "G2.OPEN_PENCIL": "打开 Pencil",
        "G2.DESIGN_PENCIL_STEPS": "按计划强交互设计 Pencil UI",
        "G2.REFRESH_SOURCE_PACK": "刷新 source pack",
        "G2.REVIEW_SOURCE_PACK": "审查 source pack",
        "G2.EXTRACT_PENCIL_FRAMES": "提取 Pencil frames",
        "G2.MAP_FEATURE_TO_PENCIL_FRAME": "映射功能到 Pencil frame",
        "G2.CHECK_FEATURE_UI_MAP": "校验 feature-ui-map",
        "G2.DRAFT_DESIGN_CONTRACT": "生成 G2 设计合同",
        "G2.DELIVER_PENCIL_DESIGN": "交付 Pencil 设计稿",
        "G2.WRITE_DESIGN_ARTIFACT": "生成 02-design.md",
        "G2.READINESS_CHECK": "G2 完成前校验",
        "G2.USER_APPROVAL": "用户确认 G2",
        "G2.COMPLETE": "G2 关闭",
    }
    authorities = {
        "G2.START": ["event_tree", "01-project-definition.md"],
        "G2.READ_G1_DEFINITION": ["01-project-definition.md", "event_tree"],
        "G2.CHECK_UI_REQUIREMENT": ["G1.Q4", "01-project-definition.md"],
        "G2.DRAFT_UI_DESIGN_PLAN": ["G1.Q1", "G1.Q3", "G1.Q4", "mode.json:g2_contract"],
        "G2.APPROVE_UI_DESIGN_PLAN": ["user_prompt", "mode.json:g2_contract"],
        "G2.CREATE_PENCIL_PROJECT": ["mode.json:g2_contract", "*.pen"],
        "G2.OPEN_PENCIL": ["*.pen", "pencil-desktop"],
        "G2.DESIGN_PENCIL_STEPS": ["user_prompt", "*.pen", "mode.json:g2_contract"],
        "G2.REFRESH_SOURCE_PACK": ["source-manifest.json", "frame-inventory.json", "feature-ui-map.json"],
        "G2.REVIEW_SOURCE_PACK": ["source-manifest.json", "00-source-pack.md"],
        "G2.EXTRACT_PENCIL_FRAMES": ["frame-inventory.json", "*.pen"],
        "G2.MAP_FEATURE_TO_PENCIL_FRAME": ["feature-ui-map.json", "frame-inventory.json"],
        "G2.CHECK_FEATURE_UI_MAP": ["feature-ui-map.json"],
        "G2.DRAFT_DESIGN_CONTRACT": ["mode.json:g2_contract", "event_tree"],
        "G2.DELIVER_PENCIL_DESIGN": ["*.pen", "frame-inventory.json", "feature-ui-map.json"],
        "G2.WRITE_DESIGN_ARTIFACT": ["mode.json:g2_contract", "02-design.md"],
        "G2.READINESS_CHECK": ["event_tree", "mode.json:g2_contract", "02-design.md"],
        "G2.USER_APPROVAL": ["user_prompt"],
        "G2.COMPLETE": ["event_tree"],
    }
    policies = {
        "G2.APPROVE_UI_DESIGN_PLAN": "user_only",
        "G2.CREATE_PENCIL_PROJECT": "ui_requires_project_specific_pen",
        "G2.OPEN_PENCIL": "ui_requires_pencil_open",
        "G2.DESIGN_PENCIL_STEPS": "hold_until_user_design_done_signal",
        "G2.EXTRACT_PENCIL_FRAMES": "ui_requires_frame_inventory",
        "G2.MAP_FEATURE_TO_PENCIL_FRAME": "ui_features_require_real_frame_ids",
        "G2.CHECK_FEATURE_UI_MAP": "feature_ui_map_must_be_ok_for_ui",
        "G2.DELIVER_PENCIL_DESIGN": "pencil_design_before_text_deliverable",
        "G2.USER_APPROVAL": "user_only",
        "G2.COMPLETE": "advance_to_g3",
    }
    nodes: list[dict[str, Any]] = []
    for index, event_id in enumerate(G2_EVENT_IDS):
        next_event = G2_EVENT_IDS[index + 1] if index + 1 < len(G2_EVENT_IDS) else None
        nodes.append(
            _node(
                event_id,
                parent="G2",
                phase="G2",
                kind="gate" if event_id not in {"G2.USER_APPROVAL", "G2.COMPLETE"} else event_id.rsplit(".", 1)[1].lower(),
                status="pending",
                title=titles[event_id],
                next_event=next_event,
                authority=authorities[event_id],
                artifact="02-design.md",
                hook_policy=policies.get(event_id, "must_complete_active_event"),
            )
        )
    nodes.append(
        _node(
            "G2.DESIGN_PENCIL_STEPS.ITEMS",
            parent="G2.DESIGN_PENCIL_STEPS",
            phase="G2",
            kind="design_item_group",
            status="pending",
            title="UI design items pending approved G2 design plan",
            authority=["mode.json:g2_contract.ui_plan", "user_prompt", "*.pen"],
            artifact="02-design.md",
            hook_policy="materialize_from_approved_ui_plan",
        )
    )
    return nodes


def g3_event_nodes() -> list[dict[str, Any]]:
    titles = {
        "G3.START": "启动 G3",
        "G3.READ_G1_G2_DELIVERABLES": "读取 G1/G2 交付物",
        "G3.CHECK_G2_APPROVED": "确认 G2 已通过",
        "G3.LOAD_PENCIL_AUTHORITY": "加载 Pencil 权威设计稿",
        "G3.SCAN_IMPLEMENTATION_SURFACE": "扫描代码实现面",
        "G3.MAP_PENCIL_TO_CODE_TARGETS": "映射 Pencil 到代码目标",
        "G3.CHECK_UI_CODE_MAP": "校验 ui-code-map",
        "G3.EXTRACT_LAYOUT_SPEC": "提取 UI layout spec",
        "G3.EXTRACT_DESIGN_TOKENS": "提取 design tokens",
        "G3.MAP_INTERACTION_STATES": "映射交互状态",
        "G3.WRITE_VISUAL_ACCEPTANCE": "生成视觉验收合同",
        "G3.CHECK_UI_IMPLEMENTATION_CONTRACT": "校验 UI 实现合同",
        "G3.MATERIALIZE_WORK_ITEMS": "生成 G4 work items",
        "G3.DRAFT_EXECUTION_PLAN": "编制执行计划",
        "G3.CHECK_EXECUTION_PLAN": "校验执行计划",
        "G3.WRITE_PLAN_ARTIFACT": "生成 04-plan.md",
        "G3.READINESS_CHECK": "G3 完成前校验",
        "G3.USER_APPROVAL": "用户确认 G3",
        "G3.COMPLETE": "G3 关闭",
    }
    authorities = {
        "G3.START": ["event_tree", "02-design.md"],
        "G3.READ_G1_G2_DELIVERABLES": ["01-project-definition.md", "02-design.md", "mode.json:g2_contract"],
        "G3.CHECK_G2_APPROVED": ["mode.json:g2_approval", "event_tree"],
        "G3.LOAD_PENCIL_AUTHORITY": ["*.pen", "frame-inventory.json", "feature-ui-map.json"],
        "G3.SCAN_IMPLEMENTATION_SURFACE": ["source-manifest.json", "G1.Q7", "project files"],
        "G3.MAP_PENCIL_TO_CODE_TARGETS": ["frame-inventory.json", "feature-ui-map.json", "mode.json:g3_contract"],
        "G3.CHECK_UI_CODE_MAP": ["ui-code-map.json", "feature-ui-map.json"],
        "G3.EXTRACT_LAYOUT_SPEC": ["*.pen", "frame-inventory.json", "ui-code-map.json"],
        "G3.EXTRACT_DESIGN_TOKENS": ["*.pen", "frame-inventory.json", "ui-code-map.json"],
        "G3.MAP_INTERACTION_STATES": ["ui-code-map.json", "G1.Q3", "G1.Q5"],
        "G3.WRITE_VISUAL_ACCEPTANCE": ["ui-code-map.json", "ui-layout-spec.json", "design-tokens.json"],
        "G3.CHECK_UI_IMPLEMENTATION_CONTRACT": [
            "ui-code-map.json",
            "ui-layout-spec.json",
            "design-tokens.json",
            "interaction-state-map.json",
            "visual-acceptance.json",
        ],
        "G3.MATERIALIZE_WORK_ITEMS": ["ui-code-map.json", "mode.json:g3_contract"],
        "G3.DRAFT_EXECUTION_PLAN": ["implementation-plan.json", "mode.json:g3_contract"],
        "G3.CHECK_EXECUTION_PLAN": ["implementation-plan.json", "ui-code-map.json"],
        "G3.WRITE_PLAN_ARTIFACT": ["mode.json:g3_contract", "04-plan.md"],
        "G3.READINESS_CHECK": ["event_tree", "mode.json:g3_contract", "04-plan.md"],
        "G3.USER_APPROVAL": ["user_prompt"],
        "G3.COMPLETE": ["event_tree"],
    }
    policies = {
        "G3.CHECK_G2_APPROVED": "g2_must_be_approved_before_g3",
        "G3.LOAD_PENCIL_AUTHORITY": "ui_projects_require_pencil_authority",
        "G3.SCAN_IMPLEMENTATION_SURFACE": "spawn_architect",
        "G3.MAP_PENCIL_TO_CODE_TARGETS": "spawn_designer",
        "G3.CHECK_UI_CODE_MAP": "ui_code_map_must_be_ok_for_ui",
        "G3.EXTRACT_LAYOUT_SPEC": "extract_layout_contract_from_pencil",
        "G3.EXTRACT_DESIGN_TOKENS": "extract_design_tokens_from_pencil",
        "G3.MAP_INTERACTION_STATES": "map_interaction_states_from_ui_actions",
        "G3.WRITE_VISUAL_ACCEPTANCE": "write_visual_acceptance_contract",
        "G3.CHECK_UI_IMPLEMENTATION_CONTRACT": "ui_implementation_contract_must_be_complete",
        "G3.MATERIALIZE_WORK_ITEMS": "materialize_g4_work_items_from_mapping",
        "G3.DRAFT_EXECUTION_PLAN": "spawn_planner",
        "G3.CHECK_EXECUTION_PLAN": "execution_plan_must_reference_frames_and_code_targets",
        "G3.WRITE_PLAN_ARTIFACT": "write_derived_plan_artifact",
        "G3.USER_APPROVAL": "user_only",
        "G3.COMPLETE": "advance_to_g4",
    }
    nodes: list[dict[str, Any]] = []
    for index, event_id in enumerate(G3_EVENT_IDS):
        next_event = G3_EVENT_IDS[index + 1] if index + 1 < len(G3_EVENT_IDS) else None
        nodes.append(
            _node(
                event_id,
                parent="G3",
                phase="G3",
                kind="user_approval" if event_id == "G3.USER_APPROVAL" else "complete" if event_id == "G3.COMPLETE" else "gate",
                status="pending",
                title=titles[event_id],
                next_event=next_event,
                authority=authorities[event_id],
                artifact="04-plan.md",
                hook_policy=policies.get(event_id, "must_complete_active_event"),
            )
        )
    nodes.append(
        _node(
            "G3.WORK_ITEMS",
            parent="G3.MATERIALIZE_WORK_ITEMS",
            phase="G3",
            kind="work_item_group",
            status="pending",
            title="G4 work items pending G3 plan materialization",
            authority=["ui-code-map.json", "implementation-plan.json"],
            artifact="04-plan.md",
            hook_policy="materialize_from_g3_execution_plan",
        )
    )
    return nodes


def g4_event_nodes() -> list[dict[str, Any]]:
    titles = {
        "G4.START": "Start G4 execution",
        "G4.LOAD_APPROVED_PLAN": "Load approved G3 plan",
        "G4.CHECK_G3_APPROVED": "Check G3 approval",
        "G4.SPAWN_EXECUTOR": "Spawn executor",
        "G4.EXECUTE_WORK_ITEMS": "Execute work items",
        "G4.RECORD_EXECUTION_EVIDENCE": "Record execution evidence",
        "G4.OPTIONAL_POLISH": "Run optional polish bridge",
        "G4.READINESS_CHECK": "Inspector readiness check",
        "G4.COMPLETE": "Close G4 and advance to G5",
    }
    authorities = {
        "G4.START": ["event_tree", "04-plan.md"],
        "G4.LOAD_APPROVED_PLAN": ["04-plan.md", "implementation-plan.json"],
        "G4.CHECK_G3_APPROVED": ["mode.json:g3_approval", "event_tree"],
        "G4.SPAWN_EXECUTOR": ["implementation-plan.json", "mode.json:g4_contract"],
        "G4.EXECUTE_WORK_ITEMS": ["executor result", "implementation-plan.json"],
        "G4.RECORD_EXECUTION_EVIDENCE": ["05-execution.md", "implementation-plan.json"],
        "G4.OPTIONAL_POLISH": ["05-execution.md", "polish.md"],
        "G4.READINESS_CHECK": ["05-execution.md", "event_tree"],
        "G4.COMPLETE": ["event_tree"],
    }
    policies = {
        "G4.CHECK_G3_APPROVED": "g3_must_be_approved_before_execute",
        "G4.SPAWN_EXECUTOR": "spawn_executor",
        "G4.EXECUTE_WORK_ITEMS": "executor_owned_result_required",
        "G4.RECORD_EXECUTION_EVIDENCE": "execution_evidence_required",
        "G4.OPTIONAL_POLISH": "polish_bridge_or_not_applicable",
        "G4.READINESS_CHECK": "spawn_inspector_before_review",
        "G4.COMPLETE": "advance_to_g5",
    }
    nodes: list[dict[str, Any]] = []
    for index, event_id in enumerate(G4_EVENT_IDS):
        next_event = G4_EVENT_IDS[index + 1] if index + 1 < len(G4_EVENT_IDS) else None
        nodes.append(
            _node(
                event_id,
                parent="G4",
                phase="G4",
                kind="complete" if event_id == "G4.COMPLETE" else "gate",
                status="pending",
                title=titles[event_id],
                next_event=next_event,
                authority=authorities[event_id],
                artifact="05-execution.md",
                hook_policy=policies.get(event_id, "must_complete_active_event"),
            )
        )
    return nodes


def g5_event_nodes() -> list[dict[str, Any]]:
    titles = {
        "G5.START": "Start G5 review",
        "G5.LOAD_REVIEW_INPUTS": "Load review inputs",
        "G5.CHECK_G4_COMPLETE": "Check G4 completion",
        "G5.SPAWN_REVIEWER": "Spawn reviewer",
        "G5.RECORD_REVIEW_EVIDENCE": "Record review evidence",
        "G5.UI_QUALITY_REVIEW": "UI quality review",
        "G5.CHECK_REVIEW_GATE": "Check review gate",
        "G5.COMPLETE": "Close G5 and advance to G6",
    }
    authorities = {
        "G5.START": ["event_tree", "05-execution.md"],
        "G5.LOAD_REVIEW_INPUTS": [
            "01-project-definition.md",
            "02-design.md",
            "04-plan.md",
            "05-execution.md",
            "implementation-plan.json",
        ],
        "G5.CHECK_G4_COMPLETE": ["event_tree", "mode.json:g4_contract"],
        "G5.SPAWN_REVIEWER": ["05-execution.md", "04-plan.md", "mode.json:g5_contract"],
        "G5.RECORD_REVIEW_EVIDENCE": ["06-review.md", "mode.json:g5_contract"],
        "G5.UI_QUALITY_REVIEW": [
            "ui-code-map.json",
            "ui-layout-spec.json",
            "design-tokens.json",
            "visual-acceptance.json",
            "06-review.md",
        ],
        "G5.CHECK_REVIEW_GATE": ["06-review.md", "implementation-plan.json", "05-execution.md"],
        "G5.COMPLETE": ["event_tree"],
    }
    policies = {
        "G5.LOAD_REVIEW_INPUTS": "guide_reviewer_with_g1_g4_artifacts",
        "G5.CHECK_G4_COMPLETE": "g4_must_be_complete_before_review",
        "G5.SPAWN_REVIEWER": "spawn_reviewer_quality_gate",
        "G5.RECORD_REVIEW_EVIDENCE": "review_artifact_required",
        "G5.UI_QUALITY_REVIEW": "ui_projects_require_designer_review_guidance",
        "G5.CHECK_REVIEW_GATE": "review_gate_must_clear_before_verify",
        "G5.COMPLETE": "advance_to_g6",
    }
    nodes: list[dict[str, Any]] = []
    for index, event_id in enumerate(G5_EVENT_IDS):
        next_event = G5_EVENT_IDS[index + 1] if index + 1 < len(G5_EVENT_IDS) else None
        nodes.append(
            _node(
                event_id,
                parent="G5",
                phase="G5",
                kind="complete" if event_id == "G5.COMPLETE" else "gate",
                status="pending",
                title=titles[event_id],
                next_event=next_event,
                authority=authorities[event_id],
                artifact="06-review.md",
                hook_policy=policies.get(event_id, "must_complete_active_event"),
            )
        )
    return nodes


def g6_event_nodes() -> list[dict[str, Any]]:
    titles = {
        "G6.START": "Start G6 verification",
        "G6.LOAD_VERIFICATION_INPUTS": "Load verification inputs",
        "G6.CHECK_G5_COMPLETE": "Check G5 completion",
        "G6.SPAWN_VERIFIER": "Spawn verifier",
        "G6.RECORD_VERIFICATION_EVIDENCE": "Record verification evidence",
        "G6.CHECK_VERIFICATION_GATE": "Check verification gate",
        "G6.COMPLETE": "Close G6 and advance to G7",
    }
    authorities = {
        "G6.START": ["event_tree", "06-review.md"],
        "G6.LOAD_VERIFICATION_INPUTS": [
            "01-project-definition.md",
            "02-design.md",
            "04-plan.md",
            "05-execution.md",
            "06-review.md",
            "implementation-plan.json",
        ],
        "G6.CHECK_G5_COMPLETE": ["event_tree", "mode.json:g5_contract"],
        "G6.SPAWN_VERIFIER": ["06-review.md", "04-plan.md", "mode.json:g6_contract"],
        "G6.RECORD_VERIFICATION_EVIDENCE": ["07-verification.md", "mode.json:g6_contract"],
        "G6.CHECK_VERIFICATION_GATE": ["07-verification.md", "06-review.md", "implementation-plan.json"],
        "G6.COMPLETE": ["event_tree"],
    }
    policies = {
        "G6.LOAD_VERIFICATION_INPUTS": "guide_verifier_with_g1_g5_artifacts",
        "G6.CHECK_G5_COMPLETE": "g5_must_be_complete_before_verification",
        "G6.SPAWN_VERIFIER": "spawn_verifier_fresh_evidence_gate",
        "G6.RECORD_VERIFICATION_EVIDENCE": "verification_artifact_required",
        "G6.CHECK_VERIFICATION_GATE": "verification_pass_required_before_finish",
        "G6.COMPLETE": "advance_to_g7",
    }
    nodes: list[dict[str, Any]] = []
    for index, event_id in enumerate(G6_EVENT_IDS):
        next_event = G6_EVENT_IDS[index + 1] if index + 1 < len(G6_EVENT_IDS) else None
        nodes.append(
            _node(
                event_id,
                parent="G6",
                phase="G6",
                kind="complete" if event_id == "G6.COMPLETE" else "gate",
                status="pending",
                title=titles[event_id],
                next_event=next_event,
                authority=authorities[event_id],
                artifact="07-verification.md",
                hook_policy=policies.get(event_id, "must_complete_active_event"),
            )
        )
    return nodes


def g7_event_nodes() -> list[dict[str, Any]]:
    titles = {
        "G7.START": "Start G7 finish",
        "G7.LOAD_FINISH_INPUTS": "Load finish inputs",
        "G7.CHECK_G6_PASS": "Check G6 PASS verdict",
        "G7.SPAWN_INSPECTOR": "Spawn inspector",
        "G7.RECORD_INSPECTOR_REPORT": "Record inspector report",
        "G7.SPAWN_WRITER": "Spawn writer",
        "G7.WRITE_FINISH_ARTIFACTS": "Write finish artifacts",
        "G7.CHECK_FINISH_GATE": "Check finish gate",
        "G7.COMPLETE": "Close run",
    }
    authorities = {
        "G7.START": ["event_tree", "07-verification.md"],
        "G7.LOAD_FINISH_INPUTS": [
            "01-project-definition.md",
            "02-design.md",
            "04-plan.md",
            "05-execution.md",
            "06-review.md",
            "07-verification.md",
            "hook_trace",
            "event_tree",
        ],
        "G7.CHECK_G6_PASS": ["07-verification.md", "mode.json:g6_contract"],
        "G7.SPAWN_INSPECTOR": ["hook_trace", "event_tree", "mode.json"],
        "G7.RECORD_INSPECTOR_REPORT": ["inspector-report.md", "mode.json:g7_contract"],
        "G7.SPAWN_WRITER": ["07-verification.md", "inspector-report.md", "mode.json:g7_contract"],
        "G7.WRITE_FINISH_ARTIFACTS": ["08-finish.md", "retrospective.md"],
        "G7.CHECK_FINISH_GATE": ["08-finish.md", "retrospective.md", "inspector-report.md"],
        "G7.COMPLETE": ["event_tree"],
    }
    policies = {
        "G7.LOAD_FINISH_INPUTS": "guide_finish_with_pass_verification_and_full_trace",
        "G7.CHECK_G6_PASS": "g6_pass_required_before_finish",
        "G7.SPAWN_INSPECTOR": "spawn_inspector_process_audit_before_handoff",
        "G7.RECORD_INSPECTOR_REPORT": "inspector_report_required_before_writer",
        "G7.SPAWN_WRITER": "spawn_writer_finish_and_retrospective",
        "G7.WRITE_FINISH_ARTIFACTS": "finish_and_retrospective_required",
        "G7.CHECK_FINISH_GATE": "finish_gate_requires_inspector_ack_and_improvement_action",
        "G7.COMPLETE": "mark_run_complete",
    }
    nodes: list[dict[str, Any]] = []
    for index, event_id in enumerate(G7_EVENT_IDS):
        next_event = G7_EVENT_IDS[index + 1] if index + 1 < len(G7_EVENT_IDS) else None
        nodes.append(
            _node(
                event_id,
                parent="G7",
                phase="G7",
                kind="complete" if event_id == "G7.COMPLETE" else "gate",
                status="pending",
                title=titles[event_id],
                next_event=next_event,
                authority=authorities[event_id],
                artifact="08-finish.md",
                hook_policy=policies.get(event_id, "must_complete_active_event"),
            )
        )
    return nodes


def event_by_phase_artifact(phase: str) -> str | None:
    for _stage, item_phase, _title, artifact in STAGE_PHASES:
        if item_phase == phase:
            return artifact
    return None


def create_event_tree() -> list[dict[str, Any]]:
    return [
        _node(
            "RUN",
            parent=None,
            phase=None,
            kind="root",
            status="active",
            title="SuperTeam Codex run",
            authority=["mode.json:event_tree"],
            hook_policy="nested_superteam_run_forbidden",
        )
        | {"nested_run_allowed": False},
        *_phase_nodes(),
        *_g1_nodes(),
        *_g2_nodes(),
        *g3_event_nodes(),
        *g4_event_nodes(),
        *g5_event_nodes(),
        *g6_event_nodes(),
        *g7_event_nodes(),
    ]


def event_tree(mode: dict[str, Any]) -> list[dict[str, Any]]:
    tree = mode.get("event_tree")
    if not isinstance(tree, list):
        raise KeyError("mode.event_tree is missing or invalid")
    return tree


def event_by_id(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    for item in event_tree(mode):
        if item.get("id") == event_id:
            return item
    raise KeyError(f"unknown event_tree event: {event_id}")


def child_events(mode: dict[str, Any], parent: str) -> list[dict[str, Any]]:
    return [item for item in event_tree(mode) if item.get("parent") == parent]


def active_phase(mode: dict[str, Any]) -> dict[str, Any] | None:
    phases = [event_by_id(mode, phase) for phase in STAGE_TO_PHASE.values()]
    active = [item for item in phases if item.get("status") == "active"]
    return active[0] if len(active) == 1 else None


def active_event(mode: dict[str, Any], phase: str | None = None) -> dict[str, Any] | None:
    phase_id = phase
    if phase_id is None:
        active = active_phase(mode)
        phase_id = str(active.get("id")) if active else None
    if not phase_id:
        return None
    active_children = [item for item in child_events(mode, phase_id) if item.get("status") == "active"]
    return active_children[0] if len(active_children) == 1 else None


def blocked_event(mode: dict[str, Any], phase: str | None = None) -> dict[str, Any] | None:
    phase_id = phase
    if phase_id is None:
        active = active_phase(mode)
        phase_id = str(active.get("id")) if active else None
    if not phase_id:
        return None
    blocked = [item for item in child_events(mode, phase_id) if item.get("status") == "blocked"]
    return blocked[0] if blocked else None


def activate_next_event(mode: dict[str, Any], current: dict[str, Any]) -> dict[str, Any] | None:
    next_id = current.get("next")
    if not next_id:
        return None
    next_event = event_by_id(mode, str(next_id))
    if next_event.get("status") != "pending":
        raise ValueError(f"next event {next_id} is not pending")
    next_event["status"] = "active"
    return next_event


def mark_active_event_terminal(mode: dict[str, Any], event_id: str, status: str = "done") -> dict[str, Any] | None:
    if status not in EVENT_TERMINAL_STATUSES:
        raise ValueError(f"terminal status must be one of {sorted(EVENT_TERMINAL_STATUSES)}")
    current = event_by_id(mode, event_id)
    if current.get("status") != "active":
        raise ValueError(f"event {event_id} is not active")
    current["status"] = status
    return activate_next_event(mode, current)


def set_event_status(mode: dict[str, Any], event_id: str, status: str) -> dict[str, Any]:
    if status not in EVENT_STATUS_VALUES:
        raise ValueError(f"invalid event status: {status}")
    event = event_by_id(mode, event_id)
    event["status"] = status
    return event


def activate_event(mode: dict[str, Any], event_id: str) -> dict[str, Any]:
    event = event_by_id(mode, event_id)
    phase = event.get("phase")
    if phase:
        for item in child_events(mode, str(phase)):
            if item.get("status") == "active":
                item["status"] = "pending"
    event["status"] = "active"
    return event


def is_phase_complete(mode: dict[str, Any], phase: str) -> bool:
    try:
        return event_by_id(mode, f"{phase}.COMPLETE").get("status") == "done"
    except KeyError:
        return False


def transition_to_phase(mode: dict[str, Any], target_phase: str, *, force: bool = False) -> None:
    if target_phase not in PHASE_TO_STAGE:
        raise ValueError(f"unknown phase: {target_phase}")
    current = active_phase(mode)
    if current and current.get("id") != target_phase:
        if not force and not is_phase_complete(mode, str(current.get("id"))):
            raise ValueError(f"cannot leave {current.get('id')} before its COMPLETE event is done")
        current["status"] = "done"
    for _stage, phase, _title, _artifact in STAGE_PHASES:
        phase_event = event_by_id(mode, phase)
        if phase == target_phase:
            phase_event["status"] = "active"
        elif phase_event.get("status") == "active":
            phase_event["status"] = "pending" if force else "done"
        for child in child_events(mode, phase):
            if phase == target_phase:
                continue
            if child.get("status") == "active":
                child["status"] = "pending" if force else child["status"]
    target_children = child_events(mode, target_phase)
    if target_children and not any(item.get("status") == "active" for item in target_children):
        for child in target_children:
            if child.get("status") == "pending":
                child["status"] = "active"
                break
    mode["stage"] = PHASE_TO_STAGE[target_phase]


def validate_event_tree(tree: Any, stage: str | None = None) -> list[str]:
    if not isinstance(tree, list):
        return ["event_tree is missing or is not a list"]
    errors: list[str] = []
    ids: list[str] = []
    for item in tree:
        if not isinstance(item, dict):
            errors.append("event_tree contains a non-object item")
            continue
        event_id = item.get("id")
        if not isinstance(event_id, str) or not event_id:
            errors.append("event_tree contains an event without id")
            continue
        if event_id in ids:
            errors.append(f"event_tree has duplicate event id: {event_id}")
        ids.append(event_id)
        status = item.get("status")
        if status not in EVENT_STATUS_VALUES:
            errors.append(f"event {event_id!r} has invalid status: {status!r}")
        parent = item.get("parent")
        if parent is not None and parent not in ids and not any(
            isinstance(other, dict) and other.get("id") == parent for other in tree
        ):
            errors.append(f"event {event_id} references missing parent {parent!r}")
        if event_id.startswith("G1.Q") and status in EVENT_TERMINAL_STATUSES:
            if item.get("requires_answer", True) and not str(item.get("answer") or "").strip():
                errors.append(f"event {event_id} is {status} but has no answer")
    for required in ["RUN", *STAGE_TO_PHASE.values()]:
        if required not in ids:
            errors.append(f"event_tree missing required event: {required}")
    by_id = {item.get("id"): item for item in tree if isinstance(item, dict)}
    active_phases = [
        by_id.get(phase)
        for phase in STAGE_TO_PHASE.values()
        if isinstance(by_id.get(phase), dict) and by_id[phase].get("status") == "active"
    ]
    g7_done = isinstance(by_id.get("G7.COMPLETE"), dict) and by_id["G7.COMPLETE"].get("status") == "done"
    if len(active_phases) != 1 and not (g7_done and len(active_phases) == 0):
        errors.append(f"event_tree must have exactly one active global phase, found {len(active_phases)}")
    elif stage:
        expected = STAGE_TO_PHASE.get(stage)
        if expected and active_phases and active_phases[0].get("id") != expected:
            errors.append(f"mode.stage {stage!r} does not match active event_tree phase {active_phases[0].get('id')!r}")
    for phase in STAGE_TO_PHASE.values():
        children = [item for item in tree if isinstance(item, dict) and item.get("parent") == phase]
        active_children = [item for item in children if item.get("status") == "active"]
        blocked_children = [item for item in children if item.get("status") == "blocked"]
        phase_status = by_id.get(phase, {}).get("status")
        if phase_status == "active" and len(active_children) != 1 and not blocked_children:
            errors.append(f"active phase {phase} must have exactly one active child or one blocked child")
        if phase_status != "active" and active_children:
            errors.append(f"inactive phase {phase} has active child events")
    return errors


def render_event_tree_markdown(mode: dict[str, Any]) -> str:
    current_phase = active_phase(mode)
    current_event = active_event(mode) or blocked_event(mode)
    lines = [
        "## Global Workflow Context",
        "",
        f"- root_event: RUN",
        f"- current_stage: {mode.get('stage')}",
        f"- current_global_event: {current_phase.get('id') if current_phase else ''}",
        f"- current_leaf_event: {current_event.get('id') if current_event else ''}",
        "- nested_superteam_run_allowed: false",
        "",
        "| Event | Parent | Status | Artifact | Next |",
        "|---|---|---|---|---|",
    ]
    for item in event_tree(mode):
        lines.append(
            "| {id} | {parent} | {status} | {artifact} | {next} |".format(
                id=item.get("id", ""),
                parent=item.get("parent") or "",
                status=item.get("status", ""),
                artifact=item.get("artifact") or "",
                next=item.get("next") or "",
            )
        )
    return "\n".join(lines)
