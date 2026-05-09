---
name: reset
description: Safely reset SuperTeam Codex state by moving .superteam_codex to a timestamped backup.
disable-model-invocation: true
---

# SuperTeam Codex Reset

Reset does not delete state. It moves `.superteam_codex` to a timestamped backup.

Run only when the user clearly asks for a reset:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" reset --confirm
```

Report the absolute backup path.

