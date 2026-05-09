# Architecture

SuperTeam Codex is deliberately split into small runtime modules.

## Runtime Modules

- `workspace.py`: project root discovery, run paths, safe reset backup.
- `event_tree.py`: single global workflow tree for G1-G7 and nested stage gates.
- `state.py`: schema-valid `mode.json` and `project.json` reads/writes.
- `source_pack.py`: source-of-truth discovery and manifest generation.
- `frame_inventory.py`: Pencil `.pen` frame extraction.
- `feature_ui_map.py`: source document references mapped to real frames.
- `g1.py`: project-definition question gate backed by `event_tree`.
- `g2.py`: Pencil-first design gate backed by `event_tree` and `g2_contract`.
- `g3.py`: structured implementation-plan gate that maps Pencil frames,
  interaction states, visual acceptance, and code targets into G4 work items.
- `g4.py`: executor gate with TDD state, G3 UI guidance, execution evidence,
  readiness inspection, and transition to G5.
- `g5.py`: reviewer/designer gate with review evidence, UI quality guidance,
  and BLOCK return-to-G4 repair.
- `g6.py`: verifier gate with fresh evidence requirements and FAIL/INCOMPLETE
  return-to-G4 repair.
- `g7.py`: finish gate with process inspector, writer handoff, retrospective,
  and lifecycle completion.
- `tdd.py`: G4 RED/GREEN/deferred/blocked state machine and guidance messages.
- `stages.py`: high-level workflow transitions and artifact creation.
- `doctor.py`: health checks across state, sources, frame map, and gates.
- `hooks.py`: internal workflow hook-trace guard and guidance logic.
- `cli.py`: stable command surface used by skills and tests.

## Design Rules

Markdown skills never become the source of runtime truth. They describe agent
behavior and call the Python runtime. Runtime modules produce machine-readable
JSON plus concise Markdown artifacts so later agents can audit what happened.

Hook-trace is guidance-first and internal to the SuperTeam workflow. It should
expose the active event, required artifacts, role contract, TDD state, UI
contract, and evidence requirements before the agent acts. Blocking is reserved
for workflow-invalid transitions, nested runs, skipped user gates, missing
evidence at stage completion, or actions that would corrupt SuperTeam state.
The plugin does not register Codex global hooks; normal Codex sessions must not
invoke SuperTeam hook code unless the workflow CLI/skills explicitly do so.
