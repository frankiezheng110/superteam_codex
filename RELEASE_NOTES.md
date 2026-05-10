# SuperTeam Codex 1.1.5 Release Notes

Release date: 2026-05-10

## Summary

SuperTeam Codex 1.1.5 fixes Codex agent identity handling. SuperTeam roles now
bind to fixed original agent definition files and reusable role slots, so Codex
random display names cannot cause repeated agent creation for the same role.

## Release Highlights

- `mode.json.agent_roster.roles.<role>` records the original SuperTeam agent
  definition path and `rules_sha256` for every role.
- Runtime identity is `role + agent_definition_path + rules_sha256`, not the
  Codex-generated display name.
- `mode.json.agent_slots.<role>.agent_id` allows only one Codex agent instance
  per role in a run.
- Later same-role work must use `send_input`; duplicate `spawn_agent` attempts
  are rejected by state validation and native hooks.
- G1-G7 skills now require reading `agent_roster` before role calls.
- Existing 1.1.4 structured contract gates remain intact.

## Verification

```powershell
python -m compileall superteam_codex tests
python -m unittest discover -s tests
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Test-SuperTeamCodex.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\New-ReleaseArchive.ps1
```

Install or update from GitHub:

```powershell
$installer = Join-Path $env:TEMP "Install-FromGitHub.ps1"
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/frankiezheng110/superteam_codex/main/scripts/Install-FromGitHub.ps1" `
  -OutFile $installer
powershell -NoProfile -ExecutionPolicy Bypass -File $installer -Ref v1.1.5
```

## Release Asset

The clean source archive should be generated at:

```text
dist/superteam-codex-1.1.5.zip
```
