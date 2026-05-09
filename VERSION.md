# SuperTeam Codex Version

Version: 1.1.3
Release date: 2026-05-09

## Summary

Patch release that removes SuperTeam Codex from the Codex global hook surface.

This version keeps the complete G1-G7 runtime and hook-trace behavior from
1.1.2, but makes the hook boundary explicit:

- `.codex-plugin/plugin.json` exposes skills only and does not declare
  plugin-level hooks;
- SuperTeam hook logic remains internal to `superteam_codex.runtime.hooks` and
  the explicit `g1-trace` through `g7-trace` workflow rails;
- ordinary Codex sessions do not invoke SuperTeam hooks when no SuperTeam
  workflow is active;
- release packaging still excludes `.superteam_codex`, `.hook-trace-tests`,
  `dist`, `build`, `__pycache__`, and Python bytecode.
