# SuperTeam Codex Version

Version: 1.1.5
Release date: 2026-05-10

## Summary

Patch release that fixes Codex agent identity handling by binding SuperTeam
roles to fixed original agent definitions and reusable role slots.

This version keeps the structured contract gates from 1.1.4 and adds an
`agent_roster` authority so Codex random display names cannot replace
SuperTeam role identity:

- `mode.json.agent_roster.roles.<role>` binds each SuperTeam role to the
  original agent definition file path and `rules_sha256`.
- `mode.json.agent_slots.<role>.agent_id` allows only one live Codex agent
  instance per role in a run.
- Later calls to the same role must use `send_input`; duplicate `spawn_agent`
  calls for an already-bound role are rejected.
- Native hook checks block raw or duplicate `spawn_agent` when no fixed role
  slot initialization is pending.
