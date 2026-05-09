$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
  python -m unittest discover -s tests
  python -m compileall superteam_codex hooks
  python -m superteam_codex.cli --project $root status
} finally {
  Pop-Location
}

