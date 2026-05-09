---
name: g7
description: Finish a verified SuperTeam Codex run through G7 inspector and writer gates, then close the lifecycle.
argument-hint: [optional finish note]
disable-model-invocation: true
---

# SuperTeam Codex G7

Run G7 through the hook-trace rail:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g7-next
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g7-trace --signal spawn-record --agent inspector --agent-id "<id>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g7-trace --signal agent-result --agent inspector "<process audit note>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g7-trace --signal spawn-record --agent writer --agent-id "<id>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g7-trace --signal agent-result --agent writer "<finish note>"
```

G7 is finish-only. It must not modify product code. It requires verifier PASS,
an inspector report, `08-finish.md`, `retrospective.md`, inspector report
acknowledgement in the finish artifact, and a non-empty `improvement_action`.
