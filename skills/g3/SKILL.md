---
name: g3
description: Reopen or complete the SuperTeam Codex execution-plan gate.
argument-hint: [plan supplement]
disable-model-invocation: true
---

# SuperTeam Codex G3

G3 is part of the single global `mode.json.event_tree`. Its job is to consume
the approved G2 Pencil design contract and turn it into a G4 execution plan.

For UI projects, `04-plan.md` is a derived artifact. The structured authorities
are:

- `ui-code-map.json`: G2 design authority mapping Pencil frame ids to routes, pages, components,
  actions, data fields, and code targets.
- `ui-layout-spec.json`: records Pencil frame bounds, hierarchy, layout
  fields, and child relationships.
- `design-tokens.json`: records extractable colors, typography, radii, shadows,
  and the Pencil-export fallback rule.
- `interaction-state-map.json`: records required UI states for each mapped
  action.
- `visual-acceptance.json`: G2 design authority defining screenshot/layout acceptance checks for G5/G6.
- `pencil-contract-map.json`: G2 design authority binding each Pencil frame to one contract,
  code targets, reference screenshot, implementation screenshot, and visual
  report evidence.
- `implementation-plan.json`: defines the G4 work items.

Run G3 through the hook-trace rail:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g3-status
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g3-trace
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g3-trace --signal spawn-record --agent "<agent-role>" --agent-id "<agent-id>" "<spawn note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g3-trace --signal agent-result --agent "<agent-role>" "<agent result note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g3-trace --signal inspector-spawn-record --agent inspector --agent-id "<inspector-agent-id>" "<spawn note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g3-trace --signal inspector-result --agent inspector "<inspector result note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g3-trace --signal approve-g3 "<approval note>"
```

Agent definition rule: before any role call, read
`mode.json.agent_roster.roles.<role>` and treat its definition path plus
`rules_sha256` as the identity. Before any `spawn-record` or
`inspector-spawn-record`, inspect `mode.json.agent_slots`. If `architect`,
`planner`, or `inspector` already has an `agent_id`, continue that same agent
with `send_input` and record the existing id. Do not spawn a new planner for
repair, and do not spawn event-specific inspectors.

The G3 subtree is:

1. `G3.START`
2. `G3.READ_G1_G2_DELIVERABLES`
3. `G3.CHECK_G2_APPROVED`
4. `G3.LOAD_PENCIL_AUTHORITY`
5. `G3.SCAN_IMPLEMENTATION_SURFACE`
6. `G3.CHECK_UI_CODE_MAP`
7. `G3.MATERIALIZE_WORK_ITEMS`
8. `G3.DRAFT_EXECUTION_PLAN`
9. `G3.CHECK_EXECUTION_PLAN`
10. `G3.WRITE_PLAN_ARTIFACT`
11. `G3.READINESS_CHECK`
12. `G3.USER_APPROVAL`
13. `G3.COMPLETE`

`G3.WORK_ITEMS` exists as the work-item collection. Concrete
`G3.WORK_ITEMS.ITEM_001...ITEM_N` nodes are materialized only after
`G3.MATERIALIZE_WORK_ITEMS`.

Every task must include:

- source file references;
- Pencil frame ids, or `NO_UI`;
- implementation files expected to change;
- acceptance checks;
- verification commands.

Do not enter execute with unmapped UI work.

Hard constraints:

- G3 cannot rely on `02-design.md` alone for UI work and cannot regenerate G2
  design authorities.
- UI projects require `ui-code-map.json.status == ok`.
- UI projects require `ui-layout-spec.json`, `design-tokens.json`,
  `interaction-state-map.json`, and `visual-acceptance.json` status `ok`.
- UI projects require a valid G2 Pencil reference screenshot for every mapped
  top-level frame before G4 execution.
- UI projects require `pencil-contract-map.json.status == ok`, with one
  contract per mapped Pencil frame.
- Every UI work item must cite Pencil frame ids from `frame-inventory.json`.
- Every UI work item must cite `pencil-contract-map.json#contracts.<frame_id>`
  and the required screenshot/report evidence refs.
- Every UI feature mapped in `feature-ui-map.json` must resolve to code targets.
- Every UI work item must cite UI implementation `spec_refs`.
- G4 must implement UI from the G2 Pencil contract plus the G3 implementation
  plan, not from prose memory or free interpretation.
- G5 and G6 retain their normal review/verification gates and additionally
  compare implementation screenshots against G2 reference screenshots.
- `SCAN_IMPLEMENTATION_SURFACE` and `DRAFT_EXECUTION_PLAN` require real agent
  spawn/result records bound to reusable role slots.
- Every agent-owned event requires a real reusable Inspector spawn/result
  before next.
- `G3.USER_APPROVAL` can only complete after explicit user approval and
  Inspector check.
