---
name: finish
description: Finish a verified SuperTeam Codex run with delivery summary, evidence, residual risks, and next steps.
disable-model-invocation: true
---

# SuperTeam Codex Finish / G7

Finish only after verifier PASS. G7 must not modify product code. It produces
process and handoff artifacts only.

Use `g7-next` and `g7-trace` as the machine rail:

- spawn the original SuperTeam `inspector` for process audit;
- write the inspector report;
- spawn the original SuperTeam `writer`;
- write `08-finish.md` and `retrospective.md`;
- close only after the finish gate accepts verifier PASS, inspector report
  acknowledgement, and a non-empty `improvement_action`.

`08-finish.md` must summarize:

- delivered scope;
- source and UI coverage;
- commands run;
- unresolved risks;
- final user-facing paths.
