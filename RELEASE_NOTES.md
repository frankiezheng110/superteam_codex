# SuperTeam Codex 1.1.2 Release Notes

Release date: 2026-05-09

## Summary

SuperTeam Codex 1.1.2 is a patch release that fixes Codex-native plugin hook
discovery. It keeps the complete G1-G7 Codex-native runtime and hook dispatcher
behavior from 1.1.1.

## Release Highlights

- Native hook discovery now uses Codex manifest event names: `SessionStart`,
  `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, and
  `Stop`.
- Hook commands still delegate to `hooks/codex_hook.py`, preserving the existing
  SuperTeam Codex runtime and event-tree mechanism.
- Hook manifest tests now assert the Codex-native event-name surface.
- Canonical source remains `https://github.com/frankiezheng110/superteam_codex`.
- Full G1-G7 event tree and CLI surface.
- G4 execution with TDD RED/GREEN evidence and pre-work UI guidance.
- G5 review with reviewer/designer gates and return-to-G4 repair on BLOCK.
- G6 verification with fresh evidence and return-to-G4 repair on FAIL or
  INCOMPLETE.
- G7 finish with inspector report, writer handoff, retrospective, and lifecycle
  closure.
- Original SuperTeam role binding through agent-definition path and SHA-256.
- Local install script that copies the plugin and refreshes the Codex runtime
  cache without shipping transient run state.

## Verification

Run before tagging:

```powershell
python -m unittest discover -s tests
python -m compileall superteam_codex hooks
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Test-SuperTeamCodex.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\New-ReleaseArchive.ps1
```

Install or update from GitHub:

```powershell
$installer = Join-Path $env:TEMP "Install-FromGitHub.ps1"
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/frankiezheng110/superteam_codex/main/scripts/Install-FromGitHub.ps1" `
  -OutFile $installer
powershell -NoProfile -ExecutionPolicy Bypass -File $installer -Ref v1.1.2
```

## Release Asset

The clean source archive should be generated at:

```text
dist/superteam-codex-1.1.2.zip
```
