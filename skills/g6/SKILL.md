---
name: g6
description: Verify SuperTeam Codex delivery through G6 with fresh evidence and return-to-G4 repair on FAIL or INCOMPLETE.
argument-hint: [optional verification scope]
disable-model-invocation: true
---

# SuperTeam Codex G6

Run G6 through the hook-trace rail:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g6-next
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g6-trace --signal spawn-record --agent verifier --agent-id "<id>"
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" g6-trace --signal agent-result --agent verifier "<PASS|FAIL|INCOMPLETE note>"
```

G6 owns fresh verification. Do not trust G4 or G5 notes without rerunning the
relevant tests, build checks, API checks, and UI evidence checks. Only PASS can
enter G7. FAIL or INCOMPLETE returns to G4 repair and repeats G4-G5-G6.
