---
name: go
description: Start the full Codex-native SuperTeam workflow. Use when the user invokes $superteam-codex:go, $superteam_codex:go, /superteam_codex:go, or asks for end-to-end delivery with source-pack, UI-map, execution, review, verification, and finish gates.
argument-hint: [task]
disable-model-invocation: true
---

# SuperTeam Codex Go

Run the full seven-stage workflow for:

`$ARGUMENTS`

## First Action

Before implementation or planning, start the runtime:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" go $ARGUMENTS
```

Use the current working directory as `<project-root>` unless the user provided
another project path. If the task text is empty, start with a neutral task label
and then treat the user's next message as the G1 supplement.

## Workflow Contract

Follow this exact order:

`g1 -> g2 -> g3 -> execute -> review -> verify -> finish`

The single machine truth for this order is `mode.json.event_tree`. Read it
before interpreting any subtask. If a run is already active, do not start a
nested SuperTeam run for a smaller code task; attach the task to the active
global stage.

Agents are fixed role definitions for the whole run. Read
`mode.json.agent_roster.roles.<role>` before any role call; the role identity is
the definition path plus `rules_sha256`, not the Codex display name. If
`mode.json.agent_slots.<role>.agent_id` already exists, use `send_input` to
continue that agent and record the same id. Use `spawn_agent` only to initialize
a missing role slot. Never create event-specific names such as
`inspector-g2-...` or `executor-repair-...`.

Do not implement product code until G1, G2, and G3 artifacts exist in the active
run directory. For UI-bearing work, G2/G3 must include the generated
`frame-inventory` and `feature-ui-map` artifacts.

## Hard Source Rules

- Use `00-source-pack.md` and `source-manifest.json` as the source list.
- Use `frame-inventory.json` as the Pencil frame truth.
- Use `feature-ui-map.json` to decide which UI frames support each feature.
- If the map status is `blocked_missing_frames`, stop and report the missing
  frame ids instead of inventing screens.
- If the map status is `needs_explicit_mapping`, create or request a mapping
  before implementation.
- Never deliver a starter dashboard or placeholder product UI unless the user
  explicitly requested scaffold-only output.

## Main Session Role

The main session is the Orchestrator. Call fixed SuperTeam roles through
`agent_roster`; initialize a subagent only when the workflow role has no slot
yet and the work can be split into independent, bounded tasks. Every delegated
task must cite the source files and frame ids it owns.
