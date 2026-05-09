# SuperTeam Codex 1.1.0 Release Notes

Release date: 2026-05-09

## Summary

SuperTeam Codex 1.1.0 is the first complete G1-G7 Codex-native release. It
uses one global `mode.json:event_tree`, guidance-first hook-trace events, and
stage evidence gates to keep implementation aligned with source, Pencil UI
design, TDD, review, verification, and finish artifacts.

## Release Highlights

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

## Release Asset

The clean source archive should be generated at:

```text
dist/superteam-codex-1.1.0.zip
```

