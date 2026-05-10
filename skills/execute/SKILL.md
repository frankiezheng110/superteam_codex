---
name: execute
description: Execute an approved SuperTeam Codex plan with required source, UI frame, checklist, and evidence references.
argument-hint: [optional execution scope]
disable-model-invocation: true
---

# SuperTeam Codex Execute / G4

G4 is executor-owned implementation. Before editing product files, advance the
runtime to the active G4 executor/TDD gate and read:

- `04-plan.md`
- `source-manifest.json`
- `frame-inventory.json`
- `feature-ui-map.json`
- `implementation-plan.json`
- `ui-code-map.json`
- `ui-layout-spec.json`
- `design-tokens.json`
- `interaction-state-map.json`
- `visual-acceptance.json`

Execution is blocked when `feature-ui-map.json.status` is
`blocked_missing_frames`. If the status is `needs_explicit_mapping`, build or
request the mapping first.

Each implementation task must record in `05-execution.md`:

- source files consumed;
- UI frame ids consumed, or `NO_UI`;
- G2/G3 UI guidance consumed before implementation for UI work items;
- TDD RED then GREEN evidence, or an explicit deferred/blocked decision;
- files changed;
- verification command and result.

Use `g4-next` and `g4-trace` as the machine rail. Do not claim executor
completion until the runtime accepts TDD state, UI guidance state, execution
evidence, and readiness inspection.

Agent definition rule: read `mode.json.agent_roster.roles.executor` and
`mode.json.agent_roster.roles.inspector` before role calls. If
`mode.json.agent_slots.<role>.agent_id` already exists, continue that same
agent with `send_input` and record the existing id; repair work reuses the same
executor slot.
