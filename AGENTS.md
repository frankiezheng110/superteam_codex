# SuperTeam Codex Project Rules

## Hook-Trace Hard-Gate Principle

- G1-G7 每个阶段、每一个会推进状态、生成交付物、记录证据或进入下一 gate 的行为，都必须受到 hook-trace 事件、状态机、结构化契约和 evidence gate 的硬约束；不能只用自然语言说明、Markdown 声明或 agent 自述替代。
- Hook-trace 仍应在动手前暴露当前 active event 必须遵守的交付物、上下文、证据要求和下一步动作；这些要求必须被后续 gate 机器检查，缺少必要证据、映射、报告或状态记录时，流程必须阻断。
- Agent 身份必须绑定到固定定义，而不是 Codex 随机显示名：每个 run 必须先有 `mode.json.agent_roster.roles.<role>`，其中包含原始 SuperTeam agent 定义文件路径和 `rules_sha256`。同一角色首次调用只能初始化一个 `mode.json.agent_slots.<role>.agent_id`；后续同角色任务必须 `send_input` 到已绑定 agent，禁止为事件取新名字或重新 spawn 同角色 agent。
- 对 UI 实现尤其如此：G2 必须从 Pencil 设计稿生成一一映射的结构化契约；G4 开始写 UI 前，hook 必须把 G2/G3 UI 交付物绑定到当前 work item，包括 Pencil frame、layout spec、design tokens、interaction states、visual acceptance、acceptance checks、reference screenshot 和 code targets，并在 work item 完成、readiness、review、verify、finish 阶段持续校验。
- 只有当动作会破坏 SuperTeam 自身状态、嵌套启动新 run、越过明确用户 gate、重复 spawn 已绑定角色 agent，或造成不可恢复/越权风险时，才使用拦截式 hook。普通实现动作也必须受到 workflow stage、work item、evidence 和 stage completion gate 的硬约束。
