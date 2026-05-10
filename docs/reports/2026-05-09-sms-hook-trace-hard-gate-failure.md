# SMS Hook-Trace Hard-Gate Failure Report

Date: 2026-05-09

Source workspace: `C:\Users\frankie\.codex\plugin-sources\superteam_codex`

Runtime cache inspected: `C:\Users\frankie\.codex\plugins\cache\frankie-local\superteam-codex\1.1.3`

Incident project: `D:\codex\SMS`

Incident run: `D:\codex\SMS\.superteam_codex\runs\sms-g1`

## Repair Status

This report remains the incident record for the broken SMS run. The runtime has
since been hardened so G5/G6/G7 gates no longer accept Markdown verdict prose as
the authority:

- G1 emits `project-definition.json`, and G2 must read it before design work.
- G5 requires `review-contract.json` plus visual evidence for UI clearance.
- G6 requires `verification-contract.json` plus fresh test/UI evidence for
  PASS.
- G7 requires `verification-contract.json`, `inspector-audit.json`, and
  `finish-contract.json` before lifecycle close.

## Executive Conclusion

The SMS run proves that SuperTeam Codex 1.1.3 did not implement the intended per-step hard constraints for UI/Pencil quality gates.

The active runtime enforced workflow legality and artifact-existence gates, but it did not enforce the actual quality evidence required by the UI contract. In practice, the UI/Pencil constraints became natural-language guidance plus Markdown section checks.

For UI projects, this means the workflow can reach G7 with G5/G6 marked as passed while the implemented UI does not match the Pencil source of truth.

## What Was Expected

The intended SuperTeam Codex behavior for UI work was:

- G4 must read the cited Pencil frame before writing UI code.
- G4 must produce implementation evidence for each UI work item.
- G5 must independently review implementation against the cited Pencil frame and visual acceptance contract.
- G6 must independently verify fresh UI evidence before allowing PASS.
- Missing visual evidence must be a hard failure, not a reviewer concern.

## What Actually Happened

The SMS workflow generated the expected visual acceptance contract, but downstream stages did not enforce it.

`D:\codex\SMS\.superteam_codex\runs\sms-g1\visual-acceptance.json` defines 15 screenshot/layout checks. Each check requires an `implementation_screenshot` under `evidence/g6/*.png`, `comparison.mode = screenshot_and_layout`, `max_pixel_diff_ratio = 0.02`, and must match bounds, text, spacing, alignment, and colors.

Actual evidence directory contents:

- `D:\codex\SMS\.superteam_codex\runs\sms-g1\evidence\g5-repair-001\05-execution.md`
- `D:\codex\SMS\.superteam_codex\runs\sms-g1\evidence\g5-repair-001\06-review.md`

There were no `D:\codex\SMS\.superteam_codex\runs\sms-g1\evidence\g6\*.png` files. All 15 required implementation screenshots were missing.

Despite that, G6 produced:

- `D:\codex\SMS\.superteam_codex\runs\sms-g1\07-verification.md:3` -> `Verdict: PASS`
- `D:\codex\SMS\.superteam_codex\runs\sms-g1\07-verification.md:4` -> `delivery_confidence: high`
- `D:\codex\SMS\.superteam_codex\runs\sms-g1\07-verification.md:15` -> UI map coverage based on route/page/component mapping
- `D:\codex\SMS\.superteam_codex\runs\sms-g1\07-verification.md:40-44` -> UI evidence limited to HTTP smoke/login behavior/ui-code-map coverage

This is a hard-gate failure.

## Evidence From Current Runtime Implementation

### Native Hook Boundary Is Too Narrow

`C:\Users\frankie\.codex\plugins\cache\frankie-local\superteam-codex\1.1.3\AGENTS.md:5-8` says hook-trace emphasizes front-loaded guidance, while hard constraints are limited to workflow legality, artifact gates, and stage completion gates. It explicitly says intercepting hooks should only be used for destructive SuperTeam state risks, nested runs, bypassing explicit user gates, or irreversible/privilege risks.

`C:\Users\frankie\.codex\plugins\cache\frankie-local\superteam-codex\1.1.3\superteam_codex\runtime\hooks.py:181-230` confirms the native hook only blocks:

- nested SuperTeam runs,
- writes during G1/G2/G3 except allowed SuperTeam/Pencil paths,
- stopping while execute/review/verify is still active.

During G4 execute-stage code writing, the hook returns guidance via `write_guidance_message(...)` but does not block missing UI evidence.

### G3 Creates Visual Acceptance But Only Validates Contract Shape

`runtime\g3.py:835-862` creates `visual-acceptance.json` checks with:

- `implementation_screenshot = evidence/g6/<frame>-implementation.png`
- `comparison.mode = screenshot_and_layout`
- `max_pixel_diff_ratio = 0.02`
- `must_match = bounds, text, spacing, alignment, colors`

`runtime\g3.py:1342-1363` checks only that `visual-acceptance.json` exists, has `status: ok`, includes checks, and covers mapped UI frames. It does not create or validate screenshots.

### G5 Gate Checks Report Shape, Not Visual Evidence

`runtime\g5.py:468-487` implements `review_gate_errors(...)`. It checks:

- `06-review.md` verdict is `CLEAR`, `CLEAR_WITH_CONCERNS`, or `BLOCK`;
- Delivery Scope Check section exists;
- TDD Gate section exists;
- Checklist Coverage section exists;
- UI project has a UI Quality Gate section;
- designer participation result exists.

It does not check:

- any `visual-acceptance.json` screenshot path,
- any `evidence/g6/*.png`,
- any image diff report,
- any Pencil export/reference comparison,
- whether the designer actually compared rendered UI to Pencil.

### G6 Gate Checks Report Shape, Not Visual Evidence

`runtime\g6.py:434-455` implements `verification_gate_errors(...)`. It checks:

- `07-verification.md` verdict is `PASS`, `FAIL`, or `INCOMPLETE`;
- Evidence Summary section exists;
- Requirement Status section exists;
- `delivery_confidence` exists;
- test command evidence exists for code-changing work;
- UI project has a UI Evidence / Visual Acceptance / Aesthetic Contract Evidence section.

It does not check:

- required `implementation_screenshot` files exist;
- screenshots are non-empty;
- screenshot dimensions match viewport;
- Pencil reference/export exists;
- pixel diff is below threshold;
- missing screenshot forces `FAIL` or `INCOMPLETE`.

### Doctor Does Not Check Visual Acceptance Execution

`runtime\doctor.py:17-88` checks mode schema, run directory, source pack, frame inventory, feature-ui-map, and version baseline. It does not check visual screenshots, visual diff, G5/G6 UI evidence, or `visual-acceptance.json` fulfillment.

### Tests Prove Text Assertions, Not Real Visual Gates

`tests\test_runtime.py:309-312` accepts a G6 PASS sample that merely states:

- Pencil frames were checked;
- layout/tokens/interaction states/visual acceptance evidence are PASS.

No PNG artifact or diff output is required by that test.

`tests\test_runtime.py:1158-1168` verifies `visual-acceptance.json` status is `ok`.

`tests\test_runtime.py:1208-1211` verifies UI work items mention `visual-acceptance.json` in acceptance checks.

These tests validate contract text and JSON shape, not execution of the visual contract.

## SMS Failure Chain

1. G2 selected `D:\codex\SMS\pencil\sms-master.pen` as the UI authority.
2. G3 generated `ui-code-map.json`, `ui-layout-spec.json`, `design-tokens.json`, `interaction-state-map.json`, and `visual-acceptance.json`.
3. G3 plan required final screenshots to satisfy `visual-acceptance.json`, but the verification commands remained only install/typecheck/build/test.
4. G4 completed UI work without producing the required `evidence/g6/*.png` screenshots.
5. G5 reviewed auth/session repair and UI smoke/route coverage, not full Pencil fidelity.
6. G6 passed on tests, HTTP smoke, login behavior, and route/page/component coverage.
7. G7 process audit accepted G6 PASS and closed the lifecycle.

The result was a completed workflow whose UI did not match the Pencil design.

## Root Cause

The implementation conflated three different concepts:

1. Guidance: tell an agent what evidence to consider.
2. Artifact existence: check Markdown/JSON files exist and have sections.
3. Hard quality gate: independently verify required evidence and fail if missing or invalid.

The current code implements 1 and 2. It does not implement 3 for UI/Pencil quality.

## Minimum Repair Requirements

Do not rerun SMS as a trusted SuperTeam delivery until these are fixed.

Required runtime repairs:

1. Add a visual acceptance validator.
   - Read `visual-acceptance.json`.
   - For every check, resolve `implementation_screenshot` relative to `run_dir`.
   - Require file existence and non-zero size.
   - Require screenshot dimensions to match the declared viewport when practical.
   - Require a machine-readable result artifact, for example `evidence/g6/visual-acceptance-report.json`.
   - Missing screenshots must block G6 PASS.

2. Harden G5.
   - `review_gate_errors(...)` must fail UI projects when visual acceptance evidence is missing.
   - `CLEAR` / `CLEAR_WITH_CONCERNS` must be impossible if required screenshots or visual reports are absent.
   - Designer result text alone must not satisfy the gate.

3. Harden G6.
   - `verification_gate_errors(...)` must verify the actual visual acceptance artifacts, not only a UI Evidence section.
   - `PASS` must be impossible if any required screenshot/diff result is missing or failing.
   - If browser/Playwright/Pencil verification is blocked, verdict must be `INCOMPLETE` or `FAIL`, not `PASS`.

4. Harden G4 evidence.
   - UI work item completion must require evidence that the cited Pencil frame/spec was loaded before implementation.
   - UI work item completion must produce or require an implementation screenshot before readiness.
   - Route/component coverage may be supporting evidence only; it must not stand in for visual fidelity.

5. Harden tests.
   - Add a failing test where `visual-acceptance.json` requires screenshots and none exist; G6 must block.
   - Add a failing test where `07-verification.md` says PASS but screenshots are absent; G6 must block.
   - Add a failing test where G5 says `CLEAR_WITH_CONCERNS` but visual evidence is absent; G5 must block.
   - Update current PASS fixtures to include real placeholder screenshot artifacts or a machine-readable visual report.

6. Harden doctor/status.
   - Doctor should warn/fail when a completed UI run has unfulfilled visual acceptance checks.
   - Status should surface missing visual evidence instead of only lifecycle completion.

## Practical Next-Session Entry Points

Recommended files to inspect first:

- `C:\Users\frankie\.codex\plugin-sources\superteam_codex\AGENTS.md`
- `C:\Users\frankie\.codex\plugin-sources\superteam_codex\superteam_codex\runtime\hooks.py`
- `C:\Users\frankie\.codex\plugin-sources\superteam_codex\superteam_codex\runtime\g5.py`
- `C:\Users\frankie\.codex\plugin-sources\superteam_codex\superteam_codex\runtime\g6.py`
- `C:\Users\frankie\.codex\plugin-sources\superteam_codex\superteam_codex\runtime\doctor.py`
- `C:\Users\frankie\.codex\plugin-sources\superteam_codex\tests\test_runtime.py`

Recommended first implementation task:

Implement `validate_visual_acceptance_evidence(mode)` as a shared runtime helper and call it from both G5 and G6 gates for UI projects. Start with file-existence/non-empty checks, then extend to screenshot dimension and diff checks.

## Notes

`D:\codex\superteam_codex` did not exist on this machine at report time. The actual source workspace was `C:\Users\frankie\.codex\plugin-sources\superteam_codex`.

There was an existing unrelated dirty file before this report was written: `C:\Users\frankie\.codex\plugin-sources\superteam_codex\skills\go\SKILL.md`. This report did not modify it.
