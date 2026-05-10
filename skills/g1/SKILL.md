---
name: g1
description: Reopen or complete the SuperTeam Codex project-definition gate.
argument-hint: [project definition supplement]
disable-model-invocation: true
---

# SuperTeam Codex G1

G1 is driven by the single global `mode.json.event_tree`. Do not create or
maintain a separate stage-local event table. The active path must be:

```text
RUN -> G1 -> <active G1 leaf event>
```

`project-definition.json` is the machine gate contract. `01-project-definition.md`
is the user-readable G1 artifact and is generated from the global event tree.

Ask only the active question:

1. `G1.Q1` - 项目想实现什么？
2. `G1.Q2` - 谁使用项目？有哪些角色？
3. `G1.Q3` - 项目具备哪些功能？
4. `G1.Q4` - 项目是否需要 UI 界面？如果需要，采用什么 UI 工具？
5. `G1.Q5` - 项目是否需要数据存储？核心数据有哪些？
6. `G1.Q6` - 项目是否需要接入外部系统或文件？
7. `G1.Q7` - 项目有什么指定技术栈、现有代码或硬性限制？

Run G1 through the hook-trace rail. Auto/interaction hooks expose OR spawn
state and Inspector state in every response:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g1-trace
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g1-trace --signal answer "<answer>"
```

After `G1.Q7`, G1 does not let the main session synthesize the project
definition directly. The hook-trace rail requires a summary agent:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g1-trace --signal spawn-record --agent prd-writer --agent-id "<agent-id>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g1-trace --signal agent-result "<summary result note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g1-trace --signal inspector-spawn-record --agent inspector --agent-id "<inspector-agent-id>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g1-trace --signal inspector-result --agent inspector "<inspector result note>"
```

Agent definition rule: before a role call, read
`mode.json.agent_roster.roles.<role>` and treat its definition path plus
`rules_sha256` as the identity. Before a `spawn-record`, inspect
`mode.json.agent_slots`. If `prd-writer` or `inspector` already has an
`agent_id`, continue that same agent with `send_input` and record the existing
id. Do not spawn event-specific inspector agents for `G1.SUMMARY` and
`G1.APPROVAL`.

Then ask the user to approve G1. Only after explicit user approval, record:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g1-trace --signal approve-g1 "<approval note>"
```

The hook-trace shape is:

```text
G1.QN: enter -> hold -> record -> next
G1.SUMMARY: enter -> spawn_required(prd-writer) -> spawn_record -> wait_result -> result_record -> inspector_required(inspector) -> inspector_spawn_record -> inspector_wait_result -> inspector_result_record -> inspector_check -> next
G1.APPROVAL: enter -> hold -> record -> inspector_required(inspector) -> inspector_spawn_record -> inspector_wait_result -> inspector_result_record -> inspector_check -> next
G1.COMPLETE: enter -> next
```

Hard constraints:

- Questions are user gates and must not spawn an agent.
- Every answer and approval must be recorded into `project-definition.json`;
  Markdown prose is not enough for G2.
- `G1.SUMMARY` requires `prd-writer`; OR must not synthesize the summary directly.
- Every `inspector_check` requires a real reusable `inspector` slot spawn
  record and agent id first; OR must not impersonate Inspector or create a new
  inspector for each event.
- Every G1 trace response must expose `orchestrator` and `inspector` fields.
- Inspector is passive: it records trace coverage/checkpoint status and does not approve or block in place of OR/user.

Legacy commands `g1-answer`, `g1-summary`, and `g1-approve` are low-level
primitives. For workflow testing, prefer `g1-trace`.
