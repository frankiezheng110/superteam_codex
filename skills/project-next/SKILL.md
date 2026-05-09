---
name: project-next
description: Advance SuperTeam Codex project tracking to the next milestone after a finished run.
argument-hint: [next milestone slug]
disable-model-invocation: true
---

# SuperTeam Codex Project Next

Before advancing, verify the current run is finished. Then update
`.superteam_codex/state/project.json` to set `current_milestone_slug` to the
requested next milestone and start a new `go` run for that milestone.

