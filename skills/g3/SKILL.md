---
name: g3
description: Reopen or complete the SuperTeam Codex execution-plan gate.
argument-hint: [plan supplement]
disable-model-invocation: true
---

# SuperTeam Codex G3

G3 is part of the single global `mode.json.event_tree`. Its job is to turn
the approved G2 Pencil design into a G4 execution plan.

For UI projects, `04-plan.md` is a derived artifact. The structured authorities
are:

- `ui-code-map.json`: maps Pencil frame ids to routes, pages, components,
  actions, data fields, and code targets.
- `ui-layout-spec.json`: records Pencil frame bounds, hierarchy, layout
  fields, and child relationships.
- `design-tokens.json`: records extractable colors, typography, radii, shadows,
  and the Pencil-export fallback rule.
- `interaction-state-map.json`: records required UI states for each mapped
  action.
- `visual-acceptance.json`: defines screenshot/layout acceptance checks for G6.
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

The G3 subtree is:

1. `G3.START`
2. `G3.READ_G1_G2_DELIVERABLES`
3. `G3.CHECK_G2_APPROVED`
4. `G3.LOAD_PENCIL_AUTHORITY`
5. `G3.SCAN_IMPLEMENTATION_SURFACE`
6. `G3.MAP_PENCIL_TO_CODE_TARGETS`
7. `G3.CHECK_UI_CODE_MAP`
8. `G3.EXTRACT_LAYOUT_SPEC`
9. `G3.EXTRACT_DESIGN_TOKENS`
10. `G3.MAP_INTERACTION_STATES`
11. `G3.WRITE_VISUAL_ACCEPTANCE`
12. `G3.CHECK_UI_IMPLEMENTATION_CONTRACT`
13. `G3.MATERIALIZE_WORK_ITEMS`
14. `G3.DRAFT_EXECUTION_PLAN`
15. `G3.CHECK_EXECUTION_PLAN`
16. `G3.WRITE_PLAN_ARTIFACT`
17. `G3.READINESS_CHECK`
18. `G3.USER_APPROVAL`
19. `G3.COMPLETE`

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

- G3 cannot rely on `02-design.md` alone for UI work.
- UI projects require `ui-code-map.json.status == ok`.
- UI projects require `ui-layout-spec.json`, `design-tokens.json`,
  `interaction-state-map.json`, and `visual-acceptance.json` status `ok`.
- Every UI work item must cite Pencil frame ids from `frame-inventory.json`.
- Every UI feature mapped in `feature-ui-map.json` must resolve to code targets.
- Every UI work item must cite UI implementation `spec_refs`.
- G4 must implement UI from the G3 UI implementation contract, not from prose
  memory or free interpretation.
- G6 must verify implementation screenshots against `visual-acceptance.json`.
- `SCAN_IMPLEMENTATION_SURFACE`, `MAP_PENCIL_TO_CODE_TARGETS`, and
  `DRAFT_EXECUTION_PLAN` require real agent spawn/result records.
- Every agent-owned event requires a real Inspector spawn/result before next.
- `G3.USER_APPROVAL` can only complete after explicit user approval and
  Inspector check.
