---
name: verify
description: Independently verify a SuperTeam Codex run after review.
disable-model-invocation: true
---

# SuperTeam Codex Verify / G6

Run fresh checks instead of trusting execution notes. Write `07-verification.md`
and the machine gate contract `verification-contract.json` with PASS, FAIL, or
INCOMPLETE.

Verification must compare:

- implemented files to source requirements;
- UI work to `feature-ui-map.json`;
- screenshots or concrete UI evidence to Pencil-derived visual acceptance
  rules when UI is in scope;
- behavior to acceptance criteria;
- tests to changed behavior;
- G5 concerns and residual risks to fresh verifier evidence.

Use `g6-next` and `g6-trace` as the machine rail. The runtime reads
`verification-contract.json`, not prose, for the final verdict. Only PASS can
enter G7. FAIL or INCOMPLETE returns the run to G4 repair and repeats
G4-G5-G6.

Agent definition rule: inspect `mode.json.agent_roster.roles.verifier` before
calling the verifier role. If `mode.json.agent_slots.verifier.agent_id` already
exists, continue that same agent with `send_input` and record the existing id;
verification retries reuse the same verifier slot.
