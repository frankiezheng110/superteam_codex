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

Agent definition rule: before calling `inspector` or `writer`, read
`mode.json.agent_roster.roles.<role>` and treat its definition path plus
`rules_sha256` as the identity. Inspect `mode.json.agent_slots`; if the role
already has an `agent_id`, continue that same agent with `send_input` and
record the existing id. G7 must reuse the process inspector slot instead of
spawning a new finish-only inspector.

G7 is finish-only. It must not modify product code. It requires verifier PASS
from `verification-contract.json`, an inspector report plus
`inspector-audit.json`, `08-finish.md`, `retrospective.md`,
`finish-contract.json`, and a non-empty `improvement_action`.
