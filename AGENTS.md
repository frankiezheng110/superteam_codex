# SuperTeam Codex Project Rules

## Hook-Trace Guidance Principle

- Hook 的重点是前置引导，而不是事后拦截。设计 G1-G7 的 hook-trace 机制时，优先让当前 active event 在动手前暴露必须遵守的交付物、上下文、证据要求和下一步动作。
- 硬约束应落在 workflow 合法路径上，例如不能完成 work item、不能提交 executor result、不能进入 readiness/review/verify/finish；不要把普通实现动作做成默认的工具级拦截。
- 对 UI 实现尤其如此：G4 开始写 UI 前，hook 必须把 G3 UI 交付物前置到当前 work item，包括 Pencil frame、layout spec、design tokens、interaction states、visual acceptance、acceptance checks 和 code targets。目标是让实现过程自然遵守设计稿，而不是等 UI 偏离后再阻断。
- 只有当动作会破坏 SuperTeam 自身状态、嵌套启动新 run、越过明确用户 gate、或造成不可恢复/越权风险时，才使用拦截式 hook。其他情况下使用 guidance、state、evidence gate 和 stage completion gate 来约束。
