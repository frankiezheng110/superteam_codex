---
name: end
description: End the active SuperTeam Codex run while preserving artifacts.
disable-model-invocation: true
---

# SuperTeam Codex End

Run:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" end
```

This marks the run inactive. It does not delete `.superteam_codex`.

