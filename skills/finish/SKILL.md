---
name: finish
description: Finish a verified SuperTeam Codex run with delivery summary, evidence, residual risks, and next steps.
disable-model-invocation: true
---

# SuperTeam Codex Finish / G7

Finish only after verifier PASS. G7 must not modify product code. It produces
process and handoff artifacts only.

Use `g7-next` and `g7-trace` as the machine rail:

- inspect `mode.json.agent_roster.roles.<role>` before every role call;
- inspect `mode.json.agent_slots` before every slot initialization;
- reuse an existing role slot with `send_input` and record the same `agent_id`;
- spawn the original SuperTeam `inspector` for process audit only if no
  inspector slot exists;
- write the inspector report and `inspector-audit.json`;
- spawn the original SuperTeam `writer` only if no writer slot exists;
- write `08-finish.md`, `retrospective.md`, and `finish-contract.json`;
- close only after the finish gate accepts verifier PASS from
  `verification-contract.json`, `inspector-audit.json`, `finish-contract.json`,
  and a non-empty `improvement_action`.

`08-finish.md` must summarize:

- delivered scope;
- source and UI coverage;
- commands run;
- unresolved risks;
- final user-facing paths.
