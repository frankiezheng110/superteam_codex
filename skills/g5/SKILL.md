---
name: g5
description: Review SuperTeam Codex G4 output through G5 reviewer and designer gates, returning to G4 repair on BLOCK.
argument-hint: [optional review note]
disable-model-invocation: true
---

# SuperTeam Codex G5

Run G5 through the hook-trace rail:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g5-next
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g5-trace --signal spawn-record --agent reviewer --agent-id "<id>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g5-trace --signal agent-result --agent reviewer "<verdict note>"
```

Agent definition rule: before calling `reviewer` or the UI `designer`, read
`mode.json.agent_roster.roles.<role>` and treat its definition path plus
`rules_sha256` as the identity. Inspect `mode.json.agent_slots`; if the role
already has an `agent_id`, continue that same agent with `send_input` and
record the existing id. BLOCK repair cycles reuse the same reviewer/designer
role slots.

For UI projects, G5 also requires designer participation for the UI quality
gate. Review against G1-G4 artifacts, TDD evidence, G2/G3 UI guidance, Pencil
frames, and visual acceptance evidence. Reviewer output must include
`review-contract.json`; that contract, plus UI visual evidence when applicable,
is the hard gate. A BLOCK verdict returns to G4 repair; do not advance to G6
after BLOCK.
