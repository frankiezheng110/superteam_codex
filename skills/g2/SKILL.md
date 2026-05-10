---
name: g2
description: Reopen or complete the SuperTeam Codex Pencil design and source-review gate.
argument-hint: [design supplement]
disable-model-invocation: true
---

# SuperTeam Codex G2

G2 is part of the single global `mode.json.event_tree`. The active path must be:

```text
RUN -> G2 -> <active G2 leaf event>
```

For UI projects, Pencil is the default authority. `02-design.md` is generated
from `event_tree` and `g2_contract`; it is a derived explanation, not the UI
source of truth.

Starting or resuming a run and operating Pencil directly are not competing
paths. Pencil edits are expected inside the active run when the leaf event is
`G2.DESIGN_PENCIL_STEPS`; the run state records and guards that interaction.

Run G2 through the hook-trace rail. Auto events advance immediately, agent-owned
events emit `spawn_required` before stopping, and user gates emit `hold` before
stopping:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-status
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace --signal spawn-record --agent "<agent-role>" --agent-id "<agent-id>" "<spawn note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace --signal agent-result --agent "<agent-role>" "<agent result note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace --signal inspector-spawn-record --agent inspector --agent-id "<inspector-agent-id>" "<spawn note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace --signal inspector-result --agent inspector "<inspector result note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace --signal approve-plan "<approval note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace --signal design-step "<Pencil design note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace --signal design-step --complete "<final Pencil design note>"
```

Agent definition rule: before any role call, read
`mode.json.agent_roster.roles.<role>` and treat its definition path plus
`rules_sha256` as the identity. Before any `spawn-record` or
`inspector-spawn-record`, inspect `mode.json.agent_slots`. If the required role
already has an `agent_id`, continue that existing agent with `send_input` and
record the same id. Do not spawn new event-specific `designer` or `inspector`
agents for each G2 leaf event.

The G2 subtree is:

1. `G2.START`
2. `G2.READ_G1_DEFINITION`
3. `G2.CHECK_UI_REQUIREMENT`
4. `G2.DRAFT_UI_DESIGN_PLAN`
5. `G2.APPROVE_UI_DESIGN_PLAN`
6. `G2.CREATE_PENCIL_PROJECT`
7. `G2.OPEN_PENCIL`
8. `G2.DESIGN_PENCIL_STEPS`
9. `G2.REFRESH_SOURCE_PACK`
10. `G2.REVIEW_SOURCE_PACK`
11. `G2.EXTRACT_PENCIL_FRAMES`
12. `G2.MAP_FEATURE_TO_PENCIL_FRAME`
13. `G2.CHECK_FEATURE_UI_MAP`
14. `G2.MAP_PENCIL_TO_CODE_TARGETS`
15. `G2.EXTRACT_LAYOUT_SPEC`
16. `G2.EXTRACT_DESIGN_TOKENS`
17. `G2.MAP_INTERACTION_STATES`
18. `G2.WRITE_VISUAL_ACCEPTANCE`
19. `G2.CHECK_UI_IMPLEMENTATION_CONTRACT`
20. `G2.WRITE_PENCIL_CONTRACT_MAP`
21. `G2.CHECK_PENCIL_CONTRACT_MAP`
22. `G2.DRAFT_DESIGN_CONTRACT`
23. `G2.DELIVER_PENCIL_DESIGN`
24. `G2.WRITE_DESIGN_ARTIFACT`
25. `G2.READINESS_CHECK`
26. `G2.USER_APPROVAL`
27. `G2.COMPLETE`

`G2.DESIGN_PENCIL_STEPS` has a project-tree child collection:

```text
G2.DESIGN_PENCIL_STEPS
└─ G2.DESIGN_PENCIL_STEPS.ITEMS
   └─ G2.DESIGN_PENCIL_STEPS.ITEM_001...ITEM_N
```

`ITEMS` exists from the start as the unknown UI design-item collection. Concrete
`ITEM_001...ITEM_N` nodes are materialized only after
`G2.APPROVE_UI_DESIGN_PLAN` records user approval for `g2_contract.ui_plan`.

Hard constraints:

- UI projects require explicit user approval for the generated UI design plan.
- `g2-trace` is the default G2 test path; `g2-next` is only a low-level event
  primitive.
- Auto nodes emit `enter -> record -> next`.
- Agent-owned nodes emit
  `enter -> spawn_required -> spawn_record -> wait_result -> result_record -> inspector_required -> inspector_spawn_record -> inspector_wait_result -> inspector_result_record -> inspector_check -> next`.
- User gates emit `enter -> hold` and stop until a matching `--signal` is
  recorded; user completion records `record -> inspector_required -> inspector_spawn_record -> inspector_wait_result -> inspector_result_record -> inspector_check -> next`.
- Every `inspector_check` requires a real reusable `inspector` slot spawn record
  and agent id first; OR must not impersonate Inspector or create a new
  inspector for each event.
- `DRAFT_UI_DESIGN_PLAN`, `REVIEW_SOURCE_PACK`, `DRAFT_DESIGN_CONTRACT`, and
  `WRITE_DESIGN_ARTIFACT` must be completed through the declared spawn signals,
  not by silent main-session synthesis inside the hook-trace path.
- `g2-status` and `g2-trace` output must expose `orchestrator.agent_calls` and
  `inspector` state so spawn and inspection are visible in the trace.
- The initial G2 project tree must contain the UI design-item collection, but
  must not invent product-specific item content before the UI design plan is
  approved.
- `G2.DESIGN_PENCIL_STEPS` must hold until the user gives the design-done signal.
- Direct Pencil operations belong inside `G2.DESIGN_PENCIL_STEPS`; do not treat
  them as run-external work.
- UI projects require a project-specific Pencil `.pen` file.
- UI projects require extracted Pencil frames.
- UI projects require `feature-ui-map.json` status `ok`.
- UI projects require `visual-acceptance.json`, `pencil-contract-map.json`,
  and one valid `evidence/g2/reference/<frame_id>-reference.png` per mapped
  Pencil frame before G2 approval.
- G3/G4/G5/G6 must cite G2 Pencil frame ids, contract refs, and reference
  screenshots for UI work, not only `02-design.md`.
- `G2.USER_APPROVAL` can only be completed with explicit user approval.

Record user approval with:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g2-trace --signal approve-g2 "<approval note>"
```

`g2-approve` marks `G2.COMPLETE` and advances the global event tree to `G3`.
