# G3 Execution Plan

Status: pending

## Structured Authorities

- G2 provides the UI design authorities below; G3 consumes them and must not
  regenerate them as planning artifacts.
- `ui-code-map.json` maps Pencil frames to code targets.
- `ui-layout-spec.json` records Pencil layout structure.
- `design-tokens.json` records extractable visual tokens.
- `interaction-state-map.json` records required UI states.
- `visual-acceptance.json` defines screenshot/layout acceptance checks.
- `pencil-contract-map.json` binds each Pencil frame to a design contract,
  reference screenshot, implementation screenshot, and visual reports.
- `implementation-plan.json` defines G4 work items.

## Tasks

Each task must include source files, frame ids or `NO_UI`, changed files,
`pencil-contract-map.json` contract refs, screenshot/report evidence refs,
acceptance checks, and verification commands.
