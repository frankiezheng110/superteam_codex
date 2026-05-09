---
name: doctor
description: Run SuperTeam Codex health checks for mode state, source pack, Pencil frame inventory, feature UI map, and version baseline.
disable-model-invocation: true
---

# SuperTeam Codex Doctor

Run:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" doctor
```

Treat `health=fail` as a blocker. A `warn` result can continue only when the
warning is not relevant to the user's task.

