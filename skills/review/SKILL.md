---
name: review
description: Review SuperTeam Codex execution against source pack, UI map, checklist, changed files, and tests.
disable-model-invocation: true
---

# SuperTeam Codex Review / G5

Read G1-G4 artifacts, changed files, source-manifest, frame inventory, feature
UI map, implementation plan, TDD state, and UI guidance records. Write findings
to `06-review.md`.

Review priorities:

1. Code implements the mapped source requirements.
2. UI code corresponds to real Pencil frame ids.
3. G4 consumed the G3 UI implementation contract before writing UI code.
4. Placeholder/starter UI was not substituted for product screens.
5. Tests and manual evidence cover the acceptance checks.
6. UI restoration is reviewed against Pencil-derived contracts and visual
   acceptance evidence.

Use `g5-next` and `g5-trace` as the machine rail. A BLOCK verdict returns the
run to G4 repair; do not continue into G6 after BLOCK.
