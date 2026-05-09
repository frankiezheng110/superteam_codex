---
name: status
description: Show the active SuperTeam Codex run status, stage, lifecycle, and source-pack summary.
disable-model-invocation: true
---

# SuperTeam Codex Status

Run:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" status
```

Report the current lifecycle, stage, task slug, run directory, and any validation
errors. Use absolute paths in the user-facing response.

