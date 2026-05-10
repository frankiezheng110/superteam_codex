---
name: review
description: Review SuperTeam Codex execution against source pack, UI map, checklist, changed files, and tests.
disable-model-invocation: true
---

# SuperTeam Codex Review / G5

Read G1-G4 artifacts, changed files, source-manifest, frame inventory, feature
UI map, implementation plan, TDD state, and UI guidance records. Write findings
to `06-review.md` and the machine gate contract `review-contract.json`.

Review priorities:

1. Code implements the mapped source requirements.
2. UI code corresponds to real Pencil frame ids.
3. G4 consumed the G2 Pencil contract and G3 implementation plan before writing UI code.
4. Placeholder/starter UI was not substituted for product screens.
5. Tests and manual evidence cover the acceptance checks.
6. UI restoration is reviewed against Pencil-derived contracts and visual
   acceptance evidence.

Use `g5-next` and `g5-trace` as the machine rail. The runtime reads
`review-contract.json`, not prose, for the CLEAR/CLEAR_WITH_CONCERNS/BLOCK
gate. A BLOCK verdict returns the run to G4 repair; do not continue into G6
after BLOCK.

Agent definition rule: inspect `mode.json.agent_roster.roles.reviewer` and
`mode.json.agent_roster.roles.designer` before role calls. If
`mode.json.agent_slots.<role>.agent_id` already exists, continue that same
agent with `send_input` and record the existing id; review retries reuse the
same role slots.
