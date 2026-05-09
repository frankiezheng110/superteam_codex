param(
  [string]$RepositoryUrl = "https://github.com/frankiezheng110/superteam_codex.git",
  [string]$Ref = "main",
  [string]$SourceRoot = (Join-Path $env:USERPROFILE ".codex\plugin-sources\superteam_codex"),
  [switch]$SkipCacheRefresh
)

$ErrorActionPreference = "Stop"

function Assert-UnderHome {
  param([string]$PathValue)
  $resolved = [System.IO.Path]::GetFullPath($PathValue)
  $homeRoot = [System.IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd('\') + '\'
  if (-not $resolved.StartsWith($homeRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write outside user profile: $resolved"
  }
}

Assert-UnderHome $SourceRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "git is required to install from GitHub."
}

$sourceResolved = [System.IO.Path]::GetFullPath($SourceRoot)
$parent = Split-Path -Parent $sourceResolved
New-Item -ItemType Directory -Path $parent -Force | Out-Null

if (Test-Path -LiteralPath $sourceResolved) {
  if (-not (Test-Path -LiteralPath (Join-Path $sourceResolved ".git"))) {
    throw "SourceRoot exists but is not a git checkout: $sourceResolved"
  }
  git -C $sourceResolved remote set-url origin $RepositoryUrl
} else {
  git clone $RepositoryUrl $sourceResolved
}

git -C $sourceResolved fetch --tags origin

$remoteBranch = git -C $sourceResolved ls-remote --heads origin $Ref
if (-not [string]::IsNullOrWhiteSpace($remoteBranch)) {
  git -C $sourceResolved checkout -B $Ref "origin/$Ref"
  git -C $sourceResolved pull --ff-only origin $Ref
} else {
  git -C $sourceResolved checkout --detach $Ref
}

$installScript = Join-Path $sourceResolved "scripts\Install-SuperTeamCodex.ps1"
if (-not (Test-Path -LiteralPath $installScript)) {
  throw "Install script is missing from GitHub checkout: $installScript"
}

$installArgs = @(
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-File",
  $installScript,
  "-SourceRoot",
  $sourceResolved,
  "-RepositoryUrl",
  ($RepositoryUrl -replace "\.git$", "")
)
if ($SkipCacheRefresh) {
  $installArgs += "-SkipCacheRefresh"
}

& powershell @installArgs

Write-Host "Canonical source: $RepositoryUrl"
Write-Host "Installed from checkout: $sourceResolved"
