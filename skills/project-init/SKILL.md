---
name: project-init
description: Initialize SuperTeam Codex project-level milestone tracking.
argument-hint: [project name and milestones]
disable-model-invocation: true
---

# SuperTeam Codex Project Init

Create project milestone state with:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" project-init --name "<name>" --milestone "<slug>"
```

Repeat `--milestone` for each planned milestone.

