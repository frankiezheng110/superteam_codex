# Operating Model

SuperTeam Codex has seven delivery stages:

1. G1 project definition
2. G2 Pencil design and source review
3. G3 execution plan
4. G4 execute
5. G5 review
6. G6 verify
7. G7 finish

The runtime does not pretend to write product code by itself. It creates and
validates the contract that the Codex agent must follow. The agent remains
responsible for implementation, but it cannot claim a valid SuperTeam delivery
unless source-pack, Pencil frame-map, execution, review, and verification
artifacts are present and consistent.

## Single Event Tree

The only runtime event table is `mode.json.event_tree`.

Do not create separate stage-local event tables such as `g1_events` or
`g2_events`. Every stage and every stage-internal gate is a node in the same
tree:

```text
RUN
├─ G1
│  ├─ G1.Q1
│  ├─ ...
│  └─ G1.COMPLETE
├─ G2
│  ├─ G2.READ_G1_DEFINITION
│  ├─ G2.CHECK_PENCIL_ORIGINAL
│  ├─ ...
│  └─ G2.COMPLETE
├─ G3
├─ G4
├─ G5
├─ G6
└─ G7
```

At runtime there is exactly one active global phase and one active leaf event
inside that phase. Hook checks must read `event_tree` first, then decide whether
the requested action is legal for the active leaf event.

This prevents nested SuperTeam runs. If the project is already inside
`RUN -> G4`, a small coding task belongs to the current G4 work item; it must
not start a new `RUN`.

## Fixed Agent Definitions And Role Slots

Agents are fixed SuperTeam role definitions, not Codex display names. Every run
materializes `mode.json.agent_roster.roles.<role>` from the original SuperTeam
agent definition file and its `rules_sha256`. The runtime treats
`role + agent_definition_path + rules_sha256` as the role identity; random
Codex UI names such as `Rawls` or `Tesla` are ignored.

During one run, every role binds to at most one
`mode.json.agent_slots.<role>.agent_id`. The first invocation for a role may use
`spawn_agent` only to initialize the missing slot. Later events for the same
role must reuse the existing agent with `send_input` and record the same
`agent_id`.

The runtime records every role invocation through `orchestrator.agent_calls`,
validates it against `agent_roster`, and stores the durable instance binding in
`agent_slots`. If a role already has a bound slot and a later signal supplies a
different real `agent_id`, or if the recorded definition path/hash drifts away
from `agent_roster`, the hook-trace path fails. This prevents `inspector`,
`designer`, `executor`, `reviewer`, `verifier`, and `writer` from being
respawned under event-specific names until the agent limit is exhausted.

## G1

G1 asks the compact project definition questions:

1. `G1.Q1` - 项目想实现什么？
2. `G1.Q2` - 谁使用项目？有哪些角色？
3. `G1.Q3` - 项目具备哪些功能？
4. `G1.Q4` - 项目是否需要 UI 界面？如果需要，采用什么 UI 工具？
5. `G1.Q5` - 项目是否需要数据存储？核心数据有哪些？
6. `G1.Q6` - 项目是否需要接入外部系统或文件？
7. `G1.Q7` - 项目有什么指定技术栈、现有代码或硬性限制？

`01-project-definition.md` is generated from `event_tree`. `G1.COMPLETE`
requires explicit user approval and advances the active global phase to `G2`.

## G2

G2 establishes the design contract. For UI projects, Pencil is the default UI
authority. UI design is a strong-interaction phase: the agent drafts the UI
plan, waits for explicit user approval, opens or creates the project-specific
Pencil file, records user-steered design progress, and only then extracts
frames and maps features.

An active run and direct Pencil operation are not alternatives. Pencil edits
are part of the active run when the current leaf event is
`G2.DESIGN_PENCIL_STEPS`; hooks audit the tool calls against that leaf event.

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
14. `G2.DRAFT_DESIGN_CONTRACT`
15. `G2.DELIVER_PENCIL_DESIGN`
16. `G2.WRITE_DESIGN_ARTIFACT`
17. `G2.READINESS_CHECK`
18. `G2.USER_APPROVAL`
19. `G2.COMPLETE`

Hard constraints:

- UI projects require explicit user approval for `G2.DRAFT_UI_DESIGN_PLAN`.
- `G2.DESIGN_PENCIL_STEPS` stays active until the user gives a design-done signal.
- Direct Pencil operations belong inside `G2.DESIGN_PENCIL_STEPS`, not outside
  the run.
- UI projects require a project-specific Pencil `.pen` file.
- UI projects require extracted Pencil frames.
- UI projects require `feature-ui-map.json` status `ok`.
- `02-design.md` is generated from `event_tree` and `g2_contract`.
- `02-design.md` is not the UI authority; Pencil frame ids are.
- `G2.COMPLETE` requires explicit user approval and advances the active global
  phase to `G3`.

## G3

G3 turns the approved G2 Pencil design into the execution contract for G4. For
UI projects, `04-plan.md` is not the only authority. The structured authorities
are:

- `ui-code-map.json` - maps Pencil frames to routes, pages, components,
  actions, data fields, and code targets.
- `ui-layout-spec.json` - records Pencil frame bounds, hierarchy, layout fields,
  and child relationships.
- `design-tokens.json` - records extractable colors, typography, radii, shadows,
  and the Pencil-export fallback rule.
- `interaction-state-map.json` - records required UI states for each mapped
  action.
- `visual-acceptance.json` - defines screenshot/layout acceptance checks for G6.
- `implementation-plan.json` - defines concrete G4 work items.
- `04-plan.md` - a derived readable plan generated from the two JSON artifacts.

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

Hard constraints:

- G3 cannot rely on `02-design.md` alone for UI work.
- UI projects require `ui-code-map.json` status `ok`.
- UI projects require `ui-layout-spec.json`, `design-tokens.json`,
  `interaction-state-map.json`, and `visual-acceptance.json` status `ok`.
- Every UI work item must cite Pencil frame ids and code targets.
- Every UI work item must cite UI implementation `spec_refs`.
- G4 must implement UI from the G3 UI implementation contract, not from prose
  memory or free interpretation.
- G6 must verify implementation screenshots against `visual-acceptance.json`.
- `SCAN_IMPLEMENTATION_SURFACE`, `MAP_PENCIL_TO_CODE_TARGETS`, and
  `DRAFT_EXECUTION_PLAN` require real agent spawn/result records bound to the
  reusable role slot.
- Every agent-owned event requires an Inspector spawn/result before the next
  event.
- `G3.COMPLETE` requires explicit user approval and advances the active global
  phase to `G4`.

## G4

G4 is the executor-owned implementation stage. Hook-trace does not wait for a
bad implementation and then block random editor actions. It guides the executor
before work starts by exposing the active G3 work item, TDD state, code targets,
Pencil frame ids, UI spec refs, visual acceptance checks, and required evidence.

The G4 subtree is:

1. `G4.START`
2. `G4.LOAD_APPROVED_PLAN`
3. `G4.CHECK_G3_APPROVED`
4. `G4.SPAWN_EXECUTOR`
5. `G4.EXECUTE_WORK_ITEMS`
6. `G4.RECORD_EXECUTION_EVIDENCE`
7. `G4.OPTIONAL_POLISH`
8. `G4.READINESS_CHECK`
9. `G4.COMPLETE`

Hard constraints:

- G4 cannot start before `G3.COMPLETE` and approved `g3_approval`.
- The main session must use the reusable SuperTeam `executor` role slot and
  bind the spawn record to the original agent file path and sha256. If the
  executor slot already exists, continue it with `send_input`; do not spawn a
  new event-specific executor.
- Code-changing work items must record RED then GREEN TDD evidence, or an
  explicit deferred/blocked state.
- UI work items must receive G3 UI guidance before implementation.
- G4 cannot submit executor result, record evidence, or enter review until TDD
  and UI guidance evidence are complete.
- If G6 returns a repair iteration, G4 must start again from `G4.START` with
  `G4.REPAIR_GUIDANCE` and repeat TDD/evidence for the corrected work.
- `G4.COMPLETE` advances the active global phase to `G5`.

## G5

G5 is the deliverable-quality review stage. It follows the original SuperTeam
authority split: `reviewer` owns project deliverable quality, while `inspector`
only audits team behavior. For UI projects, `designer` participates in the UI
quality gate before verification.

Hook-trace guidance comes before review starts. `G5.REVIEW_GUIDANCE.inputs`
lists the G1-G4 artifacts the reviewer must read. `G5.UI_REVIEW_GUIDANCE`
exposes Pencil-derived UI contracts, G3 visual acceptance rules, and G4
pre-implementation UI guidance so reviewer/designer behavior is steered before
judgment, instead of relying on a late rejection.

The G5 subtree is:

1. `G5.START`
2. `G5.LOAD_REVIEW_INPUTS`
3. `G5.CHECK_G4_COMPLETE`
4. `G5.SPAWN_REVIEWER`
5. `G5.RECORD_REVIEW_EVIDENCE`
6. `G5.UI_QUALITY_REVIEW`
7. `G5.CHECK_REVIEW_GATE`
8. `G5.COMPLETE`

Hard constraints:

- G5 cannot start before `G4.COMPLETE`.
- The main session must use the reusable SuperTeam `reviewer` role slot and
  bind the spawn record to the original agent file path and sha256.
- `06-review.md` and `review-contract.json` must be authored before reviewer
  result can close.
- `review-contract.json` is the hard gate for CLEAR, CLEAR_WITH_CONCERNS, or
  BLOCK, Delivery Scope Check, TDD Gate, and Checklist Coverage. Markdown
  review prose is not accepted as the gate authority.
- A BLOCK verdict does not enter G6. The runtime archives the current G4/G5
  artifacts, records a repair iteration, resets the active global phase to
  `G4`, and the run repeats `G4 -> G5 -> G6`.
- UI projects require `review-contract.json:ui_quality_gate`, passing visual
  review evidence, and a real reusable `designer` slot spawn/result before G5
  can close.
- `G5.COMPLETE` advances the active global phase to `G6`.

## G6

G6 is the independent verification stage. It follows the original SuperTeam
split: `verifier` owns the final fresh-evidence verdict, and review output is
only an input. G6 is where fresh test/build/spot-check evidence belongs; G5
does not start a separate test run.

Hook-trace guidance comes before verification starts. `G6.VERIFICATION_GUIDANCE.inputs`
lists the G1-G5 artifacts the verifier must read. `G6.TEST_EVIDENCE_GUIDANCE`
exposes implementation-plan verification commands and TDD state.
`G6.UI_VERIFICATION_GUIDANCE` exposes Pencil-derived UI contracts, G5 UI review
results, and visual acceptance rules so UI fidelity is verified against the
approved design instead of memory or prose.

The G6 subtree is:

1. `G6.START`
2. `G6.LOAD_VERIFICATION_INPUTS`
3. `G6.CHECK_G5_COMPLETE`
4. `G6.SPAWN_VERIFIER`
5. `G6.RECORD_VERIFICATION_EVIDENCE`
6. `G6.CHECK_VERIFICATION_GATE`
7. `G6.COMPLETE`

Hard constraints:

- G6 cannot start before `G5.COMPLETE` and completed `g5_contract`.
- The main session must use the reusable SuperTeam `verifier` role slot and
  bind the spawn record to the original agent file path and sha256.
- The verifier must write `07-verification.md` and
  `verification-contract.json` before verifier result can close.
- `verification-contract.json` is the hard gate for verdict `PASS`, `FAIL`, or
  `INCOMPLETE`, `delivery_confidence`, Evidence Summary, Requirement Status,
  fresh test evidence, and UI evidence when applicable. Markdown verification
  prose is not accepted as the gate authority.
- Only `PASS` can enter G7.
- `FAIL` or `INCOMPLETE` does not stop the run as a terminal error. The runtime
  archives the current G4/G5/G6 artifacts, records a repair iteration, resets
  the active global phase to `G4`, and the run repeats `G4 -> G5 -> G6`.
- Code-changing work requires concrete fresh test commands in
  `verification-contract.json:test_suite_evidence`; build-only or review-only
  evidence is not enough.
- UI projects require structured UI evidence in `verification-contract.json`
  plus visual acceptance evidence against Pencil-derived contracts.
- `G6.COMPLETE` advances the active global phase to `G7`.

## G7

G7 is the finish stage. It does not modify product code. It packages the run
after verifier PASS, then closes the lifecycle. The original SuperTeam split is
preserved: `inspector` audits process and role discipline; `writer` produces
finish and retrospective artifacts.

Hook-trace guidance comes before finish work starts. `G7.INSPECTOR_GUIDANCE`
exposes full hook_trace, event_tree, agent calls, and G1-G6 artifacts before
the inspector audit. `G7.FINISH_GUIDANCE` exposes verifier PASS, inspector
report, review concerns, residual risks, and handoff requirements before the
writer starts. `G7.NO_PRODUCT_CODE_CHANGE_GUIDANCE` narrows G7 to finish
artifacts.

The G7 subtree is:

1. `G7.START`
2. `G7.LOAD_FINISH_INPUTS`
3. `G7.CHECK_G6_PASS`
4. `G7.SPAWN_INSPECTOR`
5. `G7.RECORD_INSPECTOR_REPORT`
6. `G7.SPAWN_WRITER`
7. `G7.WRITE_FINISH_ARTIFACTS`
8. `G7.CHECK_FINISH_GATE`
9. `G7.COMPLETE`

Hard constraints:

- G7 cannot start before a G6 verifier `PASS` recorded in
  `verification-contract.json` and completed `g6_contract`.
- The main session must use the reusable SuperTeam `inspector` role slot before
  writer handoff and bind the spawn record to the original agent file path and
  sha256.
- The inspector report and `inspector-audit.json` must exist before the writer
  can close finish work.
- The main session must use the reusable SuperTeam `writer` role slot for
  `08-finish.md`, `retrospective.md`, and `finish-contract.json`.
- `finish-contract.json` must acknowledge verifier PASS, acknowledge
  `inspector-audit.json`, declare no product code changes, and contain a
  non-empty `improvement_action`. Markdown finish prose is not accepted as the
  finish gate authority.
- `G7.COMPLETE` sets the run lifecycle to complete and leaves no active global
  phase.
