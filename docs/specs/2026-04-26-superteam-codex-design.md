# SuperTeam Codex Design

Date: 2026-04-26
Status: approved by user

## Objective

Create `D:\codex\superteam_codex` as a new Codex-native SuperTeam version. This
is not a minimal port. It is a clean rewrite that preserves the seven-stage
delivery discipline but replaces Claude-oriented runtime assumptions with
Codex-native skills, hooks, state files, and verifiable gates.

## Architecture

The plugin has three layers:

1. Thin Codex skills under `skills/`.
2. Internal hook-trace guards invoked by the SuperTeam runtime.
3. A standard-library Python runtime under `superteam_codex/`.

Skills explain how the agent must operate and call the runtime. Internal
hook-trace guards protect against obvious workflow violations once a SuperTeam
run is active. The Python runtime owns state, source-pack discovery, Pencil
frame inventory, feature-to-UI mapping, lifecycle changes, doctor checks, and
gate validation. The plugin deliberately does not register Codex global hooks.

## Project State

Target projects use `.superteam_codex/`, never the legacy `.superteam/` runtime:

```text
.superteam_codex/
  state/
    mode.json
    project.json
  runs/<task-slug>/
    00-source-pack.md
    01-project-definition.md
    project-definition.json
    02-design.md
    03-feature-ui-map.md
    04-plan.md
    05-execution.md
    06-review.md
    review-contract.json
    07-verification.md
    verification-contract.json
    08-finish.md
    inspector-audit.json
    finish-contract.json
    source-manifest.json
    frame-inventory.json
    feature-ui-map.json
    evidence/
```

## Required Gates

- Source Pack Gate: execution cannot proceed when no source documents are found.
- UI Mapping Gate: UI-bearing work needs an explicit frame map or `NO_UI`.
- Frame Existence Gate: every referenced Pencil frame must exist in inventory.
- Checklist Consumption Gate: every execution task must cite source files and
  frame ids before write work starts.
- No Placeholder Product Gate: starter UI is allowed only for scaffold-only
  tasks.
- Version Baseline Gate: existing version directories must be detected before
  creating a new deliverable.
- Evidence Gate: review and verification must cite artifacts, tests, and map
  coverage.

## Quality Bar

The first version ships with runtime code, skills, hooks, docs, fixtures, and
tests. Validation must include standard-library unit tests and a realistic SMS
fixture that proves missing Pencil frame references are caught before execution.
