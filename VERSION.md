# SuperTeam Codex Version

Version: 1.1.2
Release date: 2026-05-09

## Summary

Patch release that fixes Codex-native plugin hook discovery.

This version keeps the complete G1-G7 runtime from 1.1.1 and updates the
native Codex hook manifest:

- plugin hook event names now use the Codex manifest names `SessionStart`,
  `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, and
  `Stop`;
- each hook still delegates to `hooks/codex_hook.py`, preserving the existing
  SuperTeam Codex runtime and event-tree behavior;
- hook manifest tests now assert the Codex-native event-name surface;
- release packaging still excludes `.superteam_codex`, `.hook-trace-tests`,
  `dist`, `build`, `__pycache__`, and Python bytecode.
