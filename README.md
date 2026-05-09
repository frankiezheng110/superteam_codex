# SuperTeam Codex

SuperTeam Codex is a complete Codex-native delivery plugin for the seven-stage
SuperTeam workflow. It uses a small Python runtime, thin Codex skills, and
guidance-first hook-trace events to keep implementation tied to source, UI,
TDD, review, verification, and finish evidence.

The runtime is source-of-truth driven:

- no implementation without a discovered source pack;
- no UI implementation without a validated Pencil frame inventory and feature-to-UI map;
- no G4 completion without TDD RED/GREEN evidence or an explicit deferred/blocked decision;
- no UI work item without pre-implementation G3 UI guidance;
- no G5/G6 pass-through after BLOCK, FAIL, or INCOMPLETE; the run returns to G4 repair;
- no G7 finish without verifier PASS, inspector report, finish handoff, and retrospective;
- no nested SuperTeam run inside an active `mode.json.event_tree`.

## Layout

```text
.codex-plugin/plugin.json        Codex plugin manifest
skills/                          Thin Codex skill entry points
hooks.json                       Codex hook manifest
hooks/codex_hook.py              Hook dispatcher
superteam_codex/                 Python runtime
templates/                       Artifact templates
tests/                           Standard-library unittest suite
docs/                            Architecture and operating model
```

## Workflow

The single machine truth is `.superteam_codex/state/mode.json:event_tree`.

```text
G1 project definition
G2 Pencil design and source review
G3 execution plan
G4 execute with TDD and UI guidance
G5 review with reviewer/designer gates
G6 verify with fresh evidence
G7 finish with inspector/writer gates
```

Hook-trace is designed to guide before work starts. Hard constraints belong to
workflow legality and evidence gates: a stage cannot complete, advance, or claim
agent results until the required artifacts and role-bound spawn records exist.

## Local Development

```powershell
cd D:\codex\superteam_codex
python -m unittest discover -s tests
python -m compileall superteam_codex hooks
python -m superteam_codex.cli --project D:\codex\superteam_codex doctor
```

## Install Locally

```powershell
cd D:\codex\superteam_codex
.\scripts\Install-SuperTeamCodex.ps1
```

The install script copies a complete plugin to
`C:\Users\frankie\plugins\superteam_codex`, updates
`C:\Users\frankie\.agents\plugins\marketplace.json`, and refreshes the versioned
runtime cache under
`C:\Users\frankie\.codex\plugins\cache\frankie-local\superteam-codex\<version>`.
Transient run state such as `.superteam_codex`, `.hook-trace-tests`, and
`__pycache__` is excluded from the install copy.

## Project Usage

From a target project:

```powershell
python D:\codex\superteam_codex\superteam_codex\cli.py --project . go "Build the product"
python D:\codex\superteam_codex\superteam_codex\cli.py --project . status
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g1-trace
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g2-next
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g3-next
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g4-next
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g4-trace --signal tdd-red --work-item WI-001 --command "npm test" --failed 1 "expected failing test"
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g4-trace --signal tdd-green --work-item WI-001 --command "npm test" --passed 1 --failed 0 "test passes"
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g5-next
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g6-next
python D:\codex\superteam_codex\superteam_codex\cli.py --project . g7-next
python D:\codex\superteam_codex\superteam_codex\cli.py --project . doctor
```

Generated state is isolated under `.superteam_codex/`.
