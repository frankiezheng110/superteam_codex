---
name: g4
description: Execute the approved SuperTeam Codex G3 plan through G4 with executor spawn, TDD, UI guidance, evidence, and readiness inspection.
argument-hint: [optional execution scope]
disable-model-invocation: true
---

# SuperTeam Codex G4

Run G4 through the hook-trace rail:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g4-next
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g4-trace --signal spawn-record --agent executor --agent-id "<id>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g4-trace --signal tdd-red --work-item "<WI>" --command "<cmd>" --failed 1 "<why red>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g4-trace --signal tdd-green --work-item "<WI>" --command "<cmd>" --passed 1 --failed 0 "<why green>"
```

G4 guidance happens before implementation. UI work must consume G3 frame ids,
layout specs, design tokens, interaction states, visual acceptance checks, and
code targets before code is written. Do not submit executor result until TDD,
UI guidance, execution evidence, and readiness inspection are complete.
