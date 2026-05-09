# SuperTeam Codex Version

Version: 1.1.1
Release date: 2026-05-09

## Summary

Patch release that makes GitHub the canonical install and update source.

This version keeps the complete G1-G7 runtime from 1.1.0 and updates the
distribution workflow:

- GitHub repository `https://github.com/frankiezheng110/superteam_codex` is the canonical install and update source;
- `scripts/Install-FromGitHub.ps1` clones or updates that repository before installing;
- local Codex plugin and runtime-cache directories remain generated installation artifacts, not the update source;
- release packaging still excludes `.superteam_codex`, `.hook-trace-tests`, `dist`, `build`, `__pycache__`, and Python bytecode.
