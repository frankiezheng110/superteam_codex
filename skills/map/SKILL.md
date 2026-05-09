---
name: map
description: Rebuild SuperTeam Codex source manifest, Pencil frame inventory, and feature-to-UI map.
disable-model-invocation: true
---

# SuperTeam Codex Map

Run:

```powershell
python "<plugin-root>\superteam_codex\cli.py" --project "<project-root>" map
```

Then inspect `frame-inventory.md` and `03-feature-ui-map.md` in the active run.
Treat missing frame references as blockers.

