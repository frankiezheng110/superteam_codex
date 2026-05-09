# Changelog

## 1.1.3 - 2026-05-09

- Removed SuperTeam Codex from the Codex global plugin hook surface.
- Kept hook-trace enforcement inside the SuperTeam runtime and explicit
  workflow commands.
- Updated packaging, docs, and tests so the plugin manifest exposes skills but
  does not declare `hooks`.

## 1.1.2 - 2026-05-09

- Fixed Codex-native plugin hook discovery by using Codex manifest event names:
  `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
  `PermissionRequest`, and `Stop`.
- Added Codex manifest event-name compatibility for the then-experimental
  plugin-hook path. This path is superseded by 1.1.3, which removes
  plugin-level hooks from the runtime surface.
- Updated hook manifest tests to assert the native event-name surface.

## 1.1.1 - 2026-05-09

- Made `https://github.com/frankiezheng110/superteam_codex` the canonical
  install and update source.
- Added `scripts/Install-FromGitHub.ps1` to clone or update the GitHub
  repository before syncing the Codex plugin and runtime cache.
- Updated README and release notes to avoid treating local development paths as
  the standard install/update source.

## 1.1.0 - 2026-05-09

- Completed the Codex-native SuperTeam G1-G7 runtime.
- Added guidance-first hook-trace behavior across planning, execution, review,
  verification, and finish stages.
- Added G4 executor flow with TDD RED/GREEN evidence and UI guidance derived
  from G3 deliverables.
- Added G5 reviewer/designer review gates with return-to-G4 repair on BLOCK.
- Added G6 verifier gate with fresh evidence and return-to-G4 repair on FAIL
  or INCOMPLETE.
- Added G7 inspector/writer finish gate, verifier PASS acknowledgement,
  retrospective requirement, and run lifecycle closure.
- Bound spawned roles to original SuperTeam agent-definition paths and SHA-256
  hashes.
- Added installation support that refreshes the installed plugin and runtime
  cache while excluding transient run state.

## 1.0.0 - 2026-05-08

- Initial Codex plugin baseline with source-pack, UI-map, and early workflow
  runtime support.
