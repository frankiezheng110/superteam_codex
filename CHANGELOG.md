# Changelog

## 1.1.5 - 2026-05-10

- Added `mode.json.agent_roster.roles.<role>` as the fixed authority for
  original SuperTeam agent definition path and `rules_sha256`.
- Made role invocation identity `role + agent_definition_path + rules_sha256`
  instead of the Codex UI display name.
- Hardened `agent_slots` so a role can initialize only one agent id per run and
  later work must reuse it with `send_input`.
- Added validation that rejects agent slot/call definition drift away from the
  fixed roster.
- Added native hook blocking for raw or duplicate `spawn_agent` calls when a
  fixed role slot is not pending.
- Updated G1-G7 skills and operating docs to require fixed agent definitions
  before role calls.

## 1.1.4 - 2026-05-09

- Added `project-definition.json` as the G1 machine contract and made G2 read
  it before design work.
- Moved Pencil-to-code UI contracts, visual acceptance, reference screenshots,
  and `pencil-contract-map.json` into the G2 design deliverable set.
- Made G3 consume G2 UI contracts to materialize G4 work items instead of
  regenerating UI design authority.
- Hardened G4/G5/G6 UI restoration with required reference screenshots,
  implementation screenshots, and visual evidence reports.
- Added `review-contract.json`, `verification-contract.json`,
  `inspector-audit.json`, and `finish-contract.json` as hard gate authorities
  so Markdown verdict prose cannot advance the workflow by itself.
- Extended doctor/status documentation and tests around structured contracts
  and UI visual evidence gates.

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
