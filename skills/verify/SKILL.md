---
name: verify
description: Independently verify a SuperTeam Codex run after review.
disable-model-invocation: true
---

# SuperTeam Codex Verify / G6

Run fresh checks instead of trusting execution notes. Write `07-verification.md`
with PASS, FAIL, or INCOMPLETE.

Verification must compare:

- implemented files to source requirements;
- UI work to `feature-ui-map.json`;
- screenshots or concrete UI evidence to Pencil-derived visual acceptance
  rules when UI is in scope;
- behavior to acceptance criteria;
- tests to changed behavior;
- G5 concerns and residual risks to fresh verifier evidence.

Use `g6-next` and `g6-trace` as the machine rail. Only PASS can enter G7.
FAIL or INCOMPLETE returns the run to G4 repair and repeats G4-G5-G6.
