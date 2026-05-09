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

## Canonical Source

The canonical install and update source is:

```text
https://github.com/frankiezheng110/superteam_codex
```

Local plugin directories and Codex runtime caches are generated installation
artifacts. Do not treat a machine-local checkout as the update source.

## Install or Update From GitHub

```powershell
$installer = Join-Path $env:TEMP "Install-FromGitHub.ps1"
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/frankiezheng110/superteam_codex/main/scripts/Install-FromGitHub.ps1" `
  -OutFile $installer
powershell -NoProfile -ExecutionPolicy Bypass -File $installer -Ref main
```

For a pinned release:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $installer -Ref v1.1.2
```

The GitHub installer clones or updates the repository under the user's Codex
source cache, then syncs the installed plugin and versioned runtime cache that
Codex loads locally. Transient run state such as `.superteam_codex`,
`.hook-trace-tests`, `dist`, `build`, and `__pycache__` is excluded from the
installed copy.

## Local Development

```powershell
git clone https://github.com/frankiezheng110/superteam_codex.git
cd superteam_codex
python -m unittest discover -s tests
python -m compileall superteam_codex
python -m superteam_codex.cli --project . doctor
```

## Project Usage

From a target project:

```powershell
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . go "Build the product"
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . status
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g1-trace
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g2-next
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g3-next
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g4-next
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g4-trace --signal tdd-red --work-item WI-001 --command "npm test" --failed 1 "expected failing test"
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g4-trace --signal tdd-green --work-item WI-001 --command "npm test" --passed 1 --failed 0 "test passes"
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g5-next
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g6-next
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . g7-next
python "$env:USERPROFILE\plugins\superteam_codex\superteam_codex\cli.py" --project . doctor
```

Generated state is isolated under `.superteam_codex/`.
