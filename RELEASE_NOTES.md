# SuperTeam Codex 1.1.3 Release Notes

Release date: 2026-05-09

## Summary

SuperTeam Codex 1.1.3 is a patch release that removes SuperTeam Codex from the
Codex global plugin hook surface. It keeps the complete G1-G7 Codex-native
runtime and internal hook-trace behavior from 1.1.2.

## Release Highlights

- The plugin manifest exposes skills only and does not declare `hooks`.
- Hook-trace enforcement remains inside `superteam_codex.runtime.hooks` and the
  explicit workflow commands.
- Ordinary Codex sessions do not invoke SuperTeam hooks when no SuperTeam
  workflow is active.
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
python -m compileall superteam_codex
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Test-SuperTeamCodex.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\New-ReleaseArchive.ps1
```

Install or update from GitHub:

```powershell
$installer = Join-Path $env:TEMP "Install-FromGitHub.ps1"
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/frankiezheng110/superteam_codex/main/scripts/Install-FromGitHub.ps1" `
  -OutFile $installer
powershell -NoProfile -ExecutionPolicy Bypass -File $installer -Ref v1.1.3
```

## Release Asset

The clean source archive should be generated at:

```text
dist/superteam-codex-1.1.3.zip
```
